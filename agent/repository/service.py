from pathlib import Path
import subprocess
import re
from agent.repository.scanner import scan_repository
from agent.repository.chunker import chunk_repository
from agent.repository.retriever import retrieve
from agent.repository.vector_store import index_chunks, clear_collection, set_active_collection, get_file_hashes, delete_file_chunks, get_files_in_collection
from agent.repository.models import IndexingStats


def index_repository(repo_path: str, collection_name: str = "repo_chunks", reset: bool = False) -> IndexingStats:
    """
    Scan a repository, chunk files, generate embeddings and store them in ChromaDB.
    Implements incremental indexing with file hashing.
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
            print(f"Warning: No chunks generated from {len(files)} files.")
    else:
        # Incremental indexing
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
        
        # Find new files and modified files
        files_to_index = []
        
        for file in files:
            if file.path not in existing_hashes:
                # New file
                files_to_index.append(file)
            elif file.file_hash != existing_hashes.get(file.path):
                # Modified file - delete old chunks first
                delete_file_chunks(file.path, collection_name)
                files_to_index.append(file)
            else:
                # Unchanged file - skip
                stats.files_skipped += 1
        
        # Find deleted files
        deleted_files = existing_files - set(current_file_map.keys())
        for file_path in deleted_files:
            deleted_count = delete_file_chunks(file_path, collection_name)
            stats.files_deleted += 1
        
        # Index new and modified files
        if files_to_index:
            chunks = chunk_repository(files_to_index)
            # Only index if we have chunks (avoid empty chunk lists)
            if chunks:
                index_chunks(chunks, collection_name)
                stats.files_indexed = len(files_to_index)
                stats.chunks_created = len(chunks)
            else:
                print(f"Warning: No chunks generated for {len(files_to_index)} files. Skipping indexing.")
        
        stats.files_deleted = len(deleted_files)
    
    # Print statistics
    print(f"Indexing Statistics for collection '{collection_name}':")
    print(f"  Files scanned: {stats.files_scanned}")
    print(f"  Files skipped (unchanged): {stats.files_skipped}")
    print(f"  Files indexed (new/modified): {stats.files_indexed}")
    print(f"  Files deleted: {stats.files_deleted}")
    print(f"  Chunks created: {stats.chunks_created}")
    
    return stats


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
        print(f"Successfully cloned {github_url} to {target_path}")
        return str(target_path)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to clone repository: {e.stderr}")
