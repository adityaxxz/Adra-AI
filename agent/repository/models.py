from pydantic import BaseModel
from typing import Optional


class RepositoryFile(BaseModel):
    path: str
    language: str
    content: str
    file_hash: str


class CodeChunk(BaseModel):
    chunk_id: str
    file_path: str
    language: str
    chunk_type: str  # "import", "class", "function", "module", "component", "heading", "generic"
    start_line: int
    end_line: int
    content: str
    class_name: Optional[str] = None
    function_name: Optional[str] = None
    file_hash: str


class EmbeddedChunk(BaseModel):
    chunk_id: str
    file_path: str
    language: str
    content: str
    embedding: list[float]


class SearchResult(BaseModel):
    chunk_id: str
    file_path: str
    language: str
    content: str
    score: float


class IndexingStats(BaseModel):
    files_scanned: int = 0
    files_skipped: int = 0
    files_indexed: int = 0
    files_deleted: int = 0
    chunks_created: int = 0
