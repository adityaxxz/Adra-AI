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
                "chunk_type": chunk.chunk_type,
                "class_name": chunk.class_name or "",
                "function_name": chunk.function_name or "",
                "file_hash": chunk.file_hash,
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


def get_file_hashes(collection_name: str = None) -> dict[str, str]:
    """Get all file hashes from the collection for incremental indexing."""
    try:
        collection = get_collection(collection_name)
        results = collection.get(
            include=["metadatas"]
        )
        
        file_hashes = {}
        for metadata in results["metadatas"]:
            file_path = metadata.get("file_path")
            file_hash = metadata.get("file_hash")
            if file_path and file_hash:
                file_hashes[file_path] = file_hash
        
        return file_hashes
    except Exception:
        return {}


def delete_file_chunks(file_path: str, collection_name: str = None) -> int:
    """Delete all chunks for a specific file. Returns number of chunks deleted."""
    try:
        collection = get_collection(collection_name)
        
        # Get all chunks for the file
        results = collection.get(
            where={"file_path": file_path},
            include=["documents"]
        )
        
        if results["ids"]:
            collection.delete(
                where={"file_path": file_path}
            )
            return len(results["ids"])
        
        return 0
    except Exception:
        return 0


def get_files_in_collection(collection_name: str = None) -> set[str]:
    """Get all file paths currently in the collection."""
    try:
        collection = get_collection(collection_name)
        results = collection.get(
            include=["metadatas"]
        )
        
        files = set()
        for metadata in results["metadatas"]:
            file_path = metadata.get("file_path")
            if file_path:
                files.add(file_path)
        
        return files
    except Exception:
        return set()
