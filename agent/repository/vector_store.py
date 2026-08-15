import logging
import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, PayloadSchemaType
from agent.repository.models import CodeChunk
from agent.repository.embeddings import embed_text

logger = logging.getLogger(__name__)

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)
_active_collection_name = "repo_chunks"


def _point_id(chunk_id: str) -> str:
    """Map an arbitrary chunk_id string to a deterministic Qdrant point ID (UUID)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def set_active_collection(collection_name: str) -> None:
    """Set the active collection name for repository-specific indexing."""
    global _active_collection_name
    _active_collection_name = collection_name


def get_active_collection() -> str:
    """Get the currently active collection name."""
    return _active_collection_name


def _ensure_collection(collection_name: str, vector_size: int) -> None:
    """Ensure a collection exists, creating it if missing (idempotent)."""
    try:
        client.get_collection(collection_name)
    except Exception:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        # Qdrant Cloud requires an explicit payload index before a field can be
        # used in a scroll/delete filter (e.g. delete_file_chunks, below).
        client.create_payload_index(
            collection_name=collection_name,
            field_name="file_path",
            field_schema=PayloadSchemaType.KEYWORD,
        )


def get_collection(collection_name: str = None) -> str:
    """Get or create a collection by name. Uses active collection if not specified.

    Returns the collection name; callers that used to receive a Chroma collection
    object should call `search()` instead of querying the return value directly.
    """
    name = collection_name or _active_collection_name
    try:
        client.get_collection(name)
    except Exception:
        # Vector size isn't known without an embedding; defer creation to index_chunks.
        pass
    return name


def index_chunks(chunks: list[CodeChunk], collection_name: str = None) -> None:
    """Index chunks into a specific collection. Uses active collection if not specified."""
    name = collection_name or _active_collection_name

    if not chunks:
        return

    points = []
    vector_size = None
    for chunk in chunks:
        vector = embed_text(chunk.content, task_type="RETRIEVAL_DOCUMENT")
        if vector_size is None:
            vector_size = len(vector)
        points.append(
            PointStruct(
                id=_point_id(chunk.chunk_id),
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "file_path": chunk.file_path,
                    "language": chunk.language,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "class_name": chunk.class_name or "",
                    "function_name": chunk.function_name or "",
                    "file_hash": chunk.file_hash,
                    "content": chunk.content,
                },
            )
        )

    _ensure_collection(name, vector_size)
    client.upsert(collection_name=name, points=points)


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
    name = collection_name or _active_collection_name
    try:
        result = client.scroll(collection_name=name, limit=10000, with_payload=True)

        file_hashes = {}
        for point in result[0]:
            file_path = point.payload.get("file_path")
            file_hash = point.payload.get("file_hash")
            if file_path and file_hash:
                file_hashes[file_path] = file_hash

        return file_hashes
    except Exception as e:
        logger.warning(f"get_file_hashes failed for collection {name!r}, treating as empty: {e}")
        return {}


def delete_file_chunks(file_path: str, collection_name: str = None) -> int:
    """Delete all chunks for a specific file. Returns number of chunks deleted."""
    name = collection_name or _active_collection_name
    try:
        result = client.scroll(
            collection_name=name,
            limit=10000,
            with_payload=False,
            scroll_filter=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
        )

        count = len(result[0])

        if count > 0:
            client.delete(
                collection_name=name,
                points_selector=Filter(
                    must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
                ),
            )

        return count
    except Exception as e:
        logger.warning(f"delete_file_chunks failed for {file_path!r} in collection {name!r}: {e}")
        return 0


def get_files_in_collection(collection_name: str = None) -> set[str]:
    """Get all file paths currently in the collection."""
    name = collection_name or _active_collection_name
    try:
        result = client.scroll(collection_name=name, limit=10000, with_payload=True)

        files = set()
        for point in result[0]:
            file_path = point.payload.get("file_path")
            if file_path:
                files.add(file_path)

        return files
    except Exception as e:
        logger.warning(f"get_files_in_collection failed for collection {name!r}, treating as empty: {e}")
        return set()


def search(query_embedding: list[float], collection_name: str = None, limit: int = 5) -> list[dict]:
    """Search for similar chunks. Returns a list of {id, score, payload} dicts."""
    name = collection_name or _active_collection_name
    try:
        response = client.query_points(
            collection_name=name,
            query=query_embedding,
            limit=limit,
            with_payload=True,
        )

        return [
            {"id": point.id, "score": point.score, "payload": point.payload}
            for point in response.points
        ]
    except Exception as e:
        logger.error(f"Vector search failed for collection {name!r}: {e}", exc_info=True)
        return []
