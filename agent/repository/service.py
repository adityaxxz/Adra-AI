import logging
import os
from pathlib import Path
import subprocess
import re
from agent.repository.scanner import scan_repository
from agent.repository.chunker import chunk_repository
from agent.repository.retriever import retrieve
from agent.repository.vector_store import index_chunks, clear_collection, set_active_collection, get_file_hashes, delete_file_chunks, get_files_in_collection, get_chunk_hashes_for_file, delete_chunk_by_id
from agent.repository.models import IndexingStats

logger = logging.getLogger(__name__)

#! Orchestration layer for repo aware RAG

def index_repository(repo_path: str, collection_name: str = "repo_chunks", reset: bool = False) -> IndexingStats:
    """
    Scan a repository, chunk files, generate embeddings and store them in Qdrant.
    Implements incremental indexing with file hashing.
    Force full re-indexing if `reset` is True. (default: False)
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

        # ── Level 2: chunk-level diff for modified files ──────────────────────
        chunks_to_embed: list = []

        for file in files_to_chunk_diff:
            from agent.repository.chunker import chunk_repository as _chunk_repo
            new_chunks = _chunk_repo([file])
            new_chunk_map = {c.chunk_id: c for c in new_chunks}

            # Stored chunk hashes for this file: {chunk_id: chunk_hash}
            stored_chunk_hashes = get_chunk_hashes_for_file(file.path, collection_name)
            stored_chunk_ids = set(stored_chunk_hashes.keys())
            new_chunk_ids = set(new_chunk_map.keys())

            # Chunks removed from the file → delete from vector store
            for removed_id in stored_chunk_ids - new_chunk_ids:
                delete_chunk_by_id(removed_id, collection_name)

            # Chunks that are new or whose content changed → re-embed
            for chunk_id, chunk in new_chunk_map.items():
                stored_hash = stored_chunk_hashes.get(chunk_id, "")
                if chunk.chunk_hash != stored_hash:
                    # Content changed or chunk is new within this file
                    if chunk_id in stored_chunk_ids:
                        delete_chunk_by_id(chunk_id, collection_name)
                    chunks_to_embed.append(chunk)
                else:
                    # Chunk content unchanged — skip (Level 2 optimisation)
                    stats.chunks_skipped += 1

            stats.files_indexed += 1

        # ── Full index for brand-new files ────────────────────────────────────
        if files_to_full_index:
            from agent.repository.chunker import chunk_repository as _chunk_repo2
            new_file_chunks = _chunk_repo2(files_to_full_index)
            chunks_to_embed.extend(new_file_chunks)
            stats.files_indexed += len(files_to_full_index)

        # ── Embed and upsert all changed/new chunks ───────────────────────────
        if chunks_to_embed:
            index_chunks(chunks_to_embed, collection_name)
            stats.chunks_created += len(chunks_to_embed)
        elif not files_to_chunk_diff and not files_to_full_index:
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


def search_repository(query: str, k: int = 5, collection_name: str = None):
    """
    Semantic search across indexed repository.
    """
    return retrieve(query=query, k=k, collection_name=collection_name)


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
