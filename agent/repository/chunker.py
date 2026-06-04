from agent.repository.models import RepositoryFile, CodeChunk
from agent.repository.code_aware_chunker import CodeAwareChunker


def chunk_file(file: RepositoryFile) -> list[CodeChunk]:
    """Chunk a file using code-aware chunking."""
    chunker = CodeAwareChunker()
    return chunker.chunk_file(file)


def chunk_repository(files: list[RepositoryFile]) -> list[CodeChunk]:
    """Chunk multiple files using code-aware chunking."""
    chunker = CodeAwareChunker()
    all_chunks = []
    
    for file in files:
        all_chunks.extend(chunker.chunk_file(file))
    
    return all_chunks
