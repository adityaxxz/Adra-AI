from pydantic import BaseModel


class RepositoryFile(BaseModel):
    path: str
    language: str
    content: str

class CodeChunk(BaseModel):
    chunk_id: str
    file_path: str
    language: str

    start_line: int
    end_line: int

    content: str


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