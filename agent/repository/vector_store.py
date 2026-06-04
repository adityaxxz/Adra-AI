import chromadb
from agent.repository.models import CodeChunk
from agent.repository.embeddings import embed_text


client = chromadb.PersistentClient(path="./chroma_db")
_active_collection_name = "repo_chunks"


def set_active_collection(collection_name: str) -> None:
    """Set the active collection name for repository-specific indexing."""
    global _active_collection_name
    _active_collection_name = collection_name


def get_active_collection() -> str:
    """Get the currently active collection name."""
    return _active_collection_name


def get_collection(collection_name: str = None) -> None:
    """Get or create a collection by name. Uses active collection if not specified."""
    name = collection_name or _active_collection_name
    return client.get_or_create_collection(name=name)


def index_chunks(chunks: list[CodeChunk], collection_name: str = None) -> None:
    """Index chunks into a specific collection. Uses active collection if not specified."""
    collection = get_collection(collection_name)

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for chunk in chunks:

        ids.append(chunk.chunk_id)

        documents.append(chunk.content)

        embeddings.append(
            embed_text(chunk.content)
        )

        metadatas.append({
                "file_path": chunk.file_path,
                "language": chunk.language,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,

            }
        )

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def clear_collection(collection_name: str = None) -> None:
    """Clear a specific collection. Uses active collection if not specified."""
    name = collection_name or _active_collection_name
    try:
        client.delete_collection(name)
    except Exception:
        # Collection doesn't exist, which is fine
        pass
