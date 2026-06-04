from pathlib import Path
import subprocess
import re
from agent.repository.scanner import scan_repository
from agent.repository.chunker import chunk_repository
from agent.repository.retriever import retrieve
from agent.repository.vector_store import index_chunks, clear_collection, set_active_collection


def index_repository(repo_path: str, collection_name: str = "repo_chunks", reset: bool = True) -> None:
    """
    Scan a repository, chunk files, generate embeddings and store them in ChromaDB.
    """
    set_active_collection(collection_name)

    repo = Path(repo_path)

    if not repo.exists():
        raise FileNotFoundError(
            f"Repository not found: {repo_path}"
        )

    files = scan_repository(repo_path)

    if not files:
        raise ValueError(
            "No supported files found."
        )

    chunks = chunk_repository(files)

    if reset:
        clear_collection(collection_name)

    index_chunks(chunks, collection_name)

    print(
        f"Indexed {len(files)} files "
        f"into {len(chunks)} chunks "
        f"in collection '{collection_name}'."
    )


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