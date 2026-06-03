from scanner import scan_repository
from chunker import chunk_repository
from vector_store import index_chunks, clear_collection
from retriever import retrieve


def index_repository(repo_path: str,reset: bool = True, ) -> None:
    files = scan_repository(repo_path)

    chunks = chunk_repository(files)

    if reset:
        clear_collection()
    
    index_chunks(chunks)



def search_repository(query: str,k: int = 5):

    return retrieve(
        query=query,
        k=k, 
    )