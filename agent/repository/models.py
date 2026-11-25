from pydantic import BaseModel
from typing import Optional

# How many chunks the agents retrieve per question. 5 missed an expected file for 5 of 14 questions on a
# realistic repo (mean file recall 0.70); 8 reached 0.94 for ~60% more context, and 10 added nothing
# (current-upgrades.md, "Retrieval recall investigation"). The eval harness reads this too, so it measures
# the pipeline's real value, not its own copy.
DEFAULT_RETRIEVAL_K = 8


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
    chunk_hash: str = ""  # whitespace-normalized hash of this chunk's content for chunk-level diffing


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


#Stats for indexing operations
class IndexingStats(BaseModel):
    files_scanned: int = 0
    files_skipped: int = 0
    files_indexed: int = 0
    files_deleted: int = 0
    chunks_created: int = 0
    chunks_skipped: int = 0  # chunks whose chunk_hash was unchanged (chunk-level diff)
