from agent.repository.models import SearchResult
from agent.repository.embeddings import embed_text
from agent.repository.vector_store import search


def retrieve(query: str, k: int = 5, collection_name: str = None) -> list[SearchResult]:
    query_embedding = embed_text(query)

    results = search(query_embedding, collection_name=collection_name, limit=k)

    search_results = []

    for result in results:
        payload = result["payload"]
        search_results.append(
            SearchResult(
                chunk_id=payload["chunk_id"],
                file_path=payload["file_path"],
                language=payload["language"],
                content=payload["content"],
                score=result["score"],
            )
        )

    return search_results
