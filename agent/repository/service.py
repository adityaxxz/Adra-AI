import logging
import os
from pathlib import Path
from typing import Callable, Optional
import subprocess
import re
from agent.repository.scanner import scan_repository
from agent.repository.chunker import chunk_repository
from agent.repository.retriever import retrieve
from agent.repository.vector_store import index_chunks, clear_collection, set_active_collection, get_file_hashes, delete_file_chunks, get_files_in_collection, get_chunk_hashes_for_file, delete_chunk_by_id, set_file_hash
from agent.repository.models import IndexingStats, DEFAULT_RETRIEVAL_K

logger = logging.getLogger(__name__)

#! Orchestration layer for repo aware RAG

def index_repository(repo_path: str, collection_name: str = "repo_chunks", reset: bool = False,
                     on_progress: Optional[Callable[[int, int], None]] = None) -> IndexingStats:
    """
    Scan a repository, chunk files, generate embeddings and store them in Qdrant.
    Implements incremental indexing with file hashing.
    Force full re-indexing if `reset` is True. (default: False)

    Incremental runs embed and store one file at a time, so a run that stops part-way (an embedding rate limit) keeps
    every file it finished and the next run picks up where it stopped. `on_progress(done, total)` is called as files
    that need embedding are finished.
    """
    set_active_collection(collection_name)

    repo = Path(repo_path)

    if not repo.exists():
        raise FileNotFoundError(
            f"Repository not found: {repo_path}"
        )

    stats = IndexingStats()

    if reset:
        # Force full re-indexing
        clear_collection(collection_name)
        files = scan_repository(repo_path)
        stats.files_scanned = len(files)
        
        if not files:
            raise ValueError("No supported files found.")
        
        chunks = chunk_repository(files)
        # Only index if we have chunks (avoid empty chunk lists)
        if chunks:
            index_chunks(chunks, collection_name)
            stats.files_indexed = len(files)
            stats.chunks_created = len(chunks)
        else:
            logger.warning(f"No chunks generated from {len(files)} files.")
    else:
        # Incremental indexing — two-level diff:
        #   Level 1 (file hash):  unchanged files are skipped entirely.
        #   Level 2 (chunk hash): for files whose file_hash changed, only
        #                         chunks whose content actually changed are
        #                         deleted and re-embedded.  Chunks with the
        #                         same whitespace-normalised hash are left
        #                         untouched, saving embedding API calls even
        #                         when a developer just adds a blank line.
        existing_hashes = get_file_hashes(collection_name)
        existing_files = get_files_in_collection(collection_name)

        files = scan_repository(repo_path)
        stats.files_scanned = len(files)

        if not files:
            # Handle case where repository is now empty but has existing files
            if existing_files:
                stats.files_deleted = len(existing_files)
                for file_path in existing_files:
                    delete_file_chunks(file_path, collection_name)
            return stats

        current_file_map = {file.path: file for file in files}

        # Separate files into: skip entirely | need chunk-level diff | brand new
        files_to_full_index = []   # new files — no existing chunks to compare
        files_to_chunk_diff = []   # file hash changed — do chunk-level diff

        for file in files:
            if file.path not in existing_hashes:
                # Brand-new file
                files_to_full_index.append(file)
            elif file.file_hash != existing_hashes.get(file.path):
                # File content changed — resolve at chunk level
                files_to_chunk_diff.append(file)
            else:
                # File unchanged — skip entirely (Level 1 optimisation)
                stats.files_skipped += 1

        # ── Level 2 (chunk diff) for modified files, then brand-new files ─────
        # One file at a time: embed and store its chunks, and only then stamp the kept chunks with the new file hash.
        # If embedding fails part-way, no file is left looking up to date while missing chunks, so the next run
        # re-diffs exactly the files that didn't finish.
        work = [(f, True) for f in files_to_chunk_diff] + [(f, False) for f in files_to_full_index]
        total = len(work)
        if on_progress and total:
            on_progress(0, total)

        for done, (file, is_modified) in enumerate(work, start=1):
            new_chunks = chunk_repository([file])
            kept: list = []
            to_embed: list = new_chunks
            if is_modified:
                new_chunk_map = {c.chunk_id: c for c in new_chunks}
                # Stored chunk hashes for this file: {chunk_id: chunk_hash}
                stored_chunk_hashes = get_chunk_hashes_for_file(file.path, collection_name)
                stored_chunk_ids = set(stored_chunk_hashes.keys())

                # Chunks removed from the file → delete from vector store
                for removed_id in stored_chunk_ids - set(new_chunk_map.keys()):
                    delete_chunk_by_id(removed_id, collection_name)

                # Chunks that are new or whose content changed → re-embed
                to_embed = []
                for chunk_id, chunk in new_chunk_map.items():
                    if chunk.chunk_hash != stored_chunk_hashes.get(chunk_id, ""):
                        if chunk_id in stored_chunk_ids:
                            delete_chunk_by_id(chunk_id, collection_name)
                        to_embed.append(chunk)
                    else:
                        # Chunk content unchanged — skip (Level 2 optimisation)
                        stats.chunks_skipped += 1
                        kept.append(chunk_id)

            if to_embed:
                index_chunks(to_embed, collection_name)
                stats.chunks_created += len(to_embed)
            # Kept chunks still carry the old file_hash; stamp the new one (payload only, no embedding), or the file's
            # chunks disagree and a later revert to the old content would be skipped while a re-embedded chunk is stale.
            set_file_hash(kept, file.file_hash, collection_name)
            stats.files_indexed += 1
            if on_progress:
                on_progress(done, total)

        if not work:
            logger.info("All files unchanged — nothing to index.")

        # ── Deleted files ─────────────────────────────────────────────────────
        deleted_files = existing_files - set(current_file_map.keys())
        for file_path in deleted_files:
            delete_file_chunks(file_path, collection_name)
        stats.files_deleted = len(deleted_files)
    
    logger.info(
        f"Indexing statistics for collection '{collection_name}': "
        f"scanned={stats.files_scanned}, skipped={stats.files_skipped}, "
        f"indexed={stats.files_indexed}, deleted={stats.files_deleted}, "
        f"chunks_created={stats.chunks_created}, chunks_skipped={stats.chunks_skipped}"
    )
    
    return stats


def snapshot_repo_files(repo_path: str) -> dict:
    """
    Read all indexable files from disk into a {path: content} map, for
    persisting into Repository.files so the repo can be rehydrated later.
    """
    files = scan_repository(repo_path)
    return {file.path.replace("\\", "/"): file.content for file in files}


def ensure_repo_on_disk(local_path: str, files: dict, repo_id: str) -> str:
    """
    Recreate the repo directory from a persisted files snapshot if the on-disk
    copy is missing or empty (e.g. an ephemeral dyno filesystem got wiped).
    Returns the path files now live at, or the original local_path unchanged
    if rehydration wasn't needed or there was no snapshot to rehydrate from.
    """
    if not files:
        return local_path

    if local_path and os.path.isdir(local_path) and any(Path(local_path).rglob("*")):
        return local_path

    target = Path(local_path) if local_path else Path(f"./temp_repos/{repo_id}")

    for rel_path, content in files.items():
        if content is None or ".." in Path(rel_path).parts:
            continue
        full_path = target / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    logger.info(f"Rehydrated {len(files)} file(s) to {target}")
    return str(target)


def search_repository(query: str, k: int = DEFAULT_RETRIEVAL_K, collection_name: str = None):
    """
    Semantic search across indexed repository.
    """
    return retrieve(query=query, k=k, collection_name=collection_name)


def clone_dir_for(repo_name: str, github_url: str) -> str:
    """Folder under temp_repos to clone into: the user's repository name, so
    re-cloning the same GitHub repo under a new name doesn't hit an existing
    folder. Falls back to the URL's repo name if the name has nothing usable."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", repo_name or "").strip(" .")
    if not safe:
        safe = github_url.rstrip("/").split("/")[-1].replace(".git", "")
    return f"./temp_repos/{safe}"


def clone_github_repo(github_url: str, target_dir: str = None) -> str:
    """
    Clone a public GitHub repository to a local directory.
    
    Args:
        github_url: GitHub repository URL (https://github.com/user/repo)
        target_dir: Optional target directory. If not provided, uses repo name.
    
    Returns:
        Path to the cloned repository.
    """
    # Extract repo name from URL
    repo_name = re.search(r'github\.com/[^/]+/([^/]+)', github_url)
    if not repo_name:
        raise ValueError(f"Invalid GitHub URL: {github_url}")
    
    repo_name = repo_name.group(1).replace('.git', '')
    
    if target_dir is None:
        target_dir = f"./temp_repos/{repo_name}"
    
    target_path = Path(target_dir)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Clone the repository
    try:
        subprocess.run(
            ["git", "clone", github_url, str(target_path)],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Successfully cloned {github_url} to {target_path}")
        return str(target_path)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to clone repository: {e.stderr}")
