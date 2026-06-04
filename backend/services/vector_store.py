from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import Optional, List, Dict, Set
import os
from agent.repository.models import CodeChunk
from agent.repository.embeddings import embed_text


class QdrantVectorStore:
    """Qdrant-based vector store for code chunks."""
    
    def __init__(self, host: str = None, port: int = None):
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.client = QdrantClient(host=self.host, port=self.port)
        self._active_collection = "repo_chunks"
        
    def set_active_collection(self, collection_name: str) -> None:
        """Set the active collection name."""
        self._active_collection = collection_name
        
    def get_active_collection(self) -> str:
        """Get the currently active collection name."""
        return self._active_collection
    
    def _ensure_collection(self, collection_name: str) -> None:
        """Ensure collection exists, create if not."""
        try:
            self.client.get_collection(collection_name)
        except Exception:
            # Collection doesn't exist, create it
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE)  # Adjust size based on embedding model
            )
    
    def index_chunks(self, chunks: List[CodeChunk], collection_name: str = None) -> None:
        """Index chunks into a specific collection."""
        collection = collection_name or self._active_collection
        self._ensure_collection(collection)
        
        points = []
        for chunk in chunks:
            points.append(PointStruct(
                id=chunk.chunk_id,
                vector=embed_text(chunk.content),
                payload={
                    "file_path": chunk.file_path,
                    "language": chunk.language,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "class_name": chunk.class_name or "",
                    "function_name": chunk.function_name or "",
                    "file_hash": chunk.file_hash,
                    "content": chunk.content
                }
            ))
        
        if points:
            self.client.upsert(collection_name=collection, points=points)
    
    def clear_collection(self, collection_name: str = None) -> None:
        """Clear a specific collection."""
        collection = collection_name or self._active_collection
        try:
            self.client.delete_collection(collection)
        except Exception:
            pass  # Collection doesn't exist
    
    def get_file_hashes(self, collection_name: str = None) -> Dict[str, str]:
        """Get all file hashes from the collection for incremental indexing."""
        collection = collection_name or self._active_collection
        try:
            self._ensure_collection(collection)
            result = self.client.scroll(
                collection_name=collection,
                limit=10000,
                with_payload=True
            )
            
            file_hashes = {}
            for point in result[0]:
                payload = point.payload
                file_path = payload.get("file_path")
                file_hash = payload.get("file_hash")
                if file_path and file_hash:
                    file_hashes[file_path] = file_hash
            
            return file_hashes
        except Exception:
            return {}
    
    def delete_file_chunks(self, file_path: str, collection_name: str = None) -> int:
        """Delete all chunks for a specific file. Returns number of chunks deleted."""
        collection = collection_name or self._active_collection
        try:
            self._ensure_collection(collection)
            
            # First, count how many points will be deleted
            result = self.client.scroll(
                collection_name=collection,
                limit=10000,
                with_payload=False,
                scroll_filter=Filter(
                    must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
                )
            )
            
            count = len(result[0])
            
            if count > 0:
                self.client.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
                    )
                )
            
            return count
        except Exception:
            return 0
    
    def get_files_in_collection(self, collection_name: str = None) -> Set[str]:
        """Get all file paths currently in the collection."""
        collection = collection_name or self._active_collection
        try:
            self._ensure_collection(collection)
            result = self.client.scroll(
                collection_name=collection,
                limit=10000,
                with_payload=True
            )
            
            files = set()
            for point in result[0]:
                payload = point.payload
                file_path = payload.get("file_path")
                if file_path:
                    files.add(file_path)
            
            return files
        except Exception:
            return set()
    
    def search(self, query: str, collection_name: str = None, limit: int = 5) -> List[Dict]:
        """Search for similar chunks."""
        collection = collection_name or self._active_collection
        try:
            self._ensure_collection(collection)
            query_vector = embed_text(query)
            
            results = self.client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=limit,
                with_payload=True
            )
            
            return [
                {
                    "score": result.score,
                    "payload": result.payload,
                    "id": result.id
                }
                for result in results
            ]
        except Exception as e:
            print(f"Error searching: {e}")
            return []


# Global instance
_vector_store: Optional[QdrantVectorStore] = None

def get_vector_store() -> QdrantVectorStore:
    """Get global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store

def set_active_collection(collection_name: str) -> None:
    """Set the active collection for the global vector store."""
    get_vector_store().set_active_collection(collection_name)

def get_active_collection() -> str:
    """Get the active collection name."""
    return get_vector_store().get_active_collection()
