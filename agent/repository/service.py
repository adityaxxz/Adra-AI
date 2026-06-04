from pathlib import Path
from scanner import scan_repository
from chunker import chunk_repository
from retriever import retrieve
from vector_store import index_chunks, clear_collection


def index_repository(repo_path: str,reset: bool = True) -> None:
    """
    Scan a repository, chunk files, generate embeddings and store them in ChromaDB.
    """

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
        clear_collection()

    index_chunks(chunks)

    print(
        f"Indexed {len(files)} files "
        f"into {len(chunks)} chunks."
    )


def search_repository( query: str, k: int = 5 ):
    """
    Semantic search across indexed repository.
    """

    return retrieve(
        query=query,
        k=k,
    )