from agent.repository.models import SearchResult
from agent.repository.embeddings import embed_text
from agent.repository.vector_store import get_collection


def retrieve(query: str, k: int = 5, collection_name: str = None) -> list[SearchResult]:
    query_embedding = embed_text(query)

    collection = get_collection(collection_name)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
    )

    search_results = []

    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for idx in range(len(ids)):

        search_results.append(
            SearchResult(
                chunk_id=ids[idx],
                file_path=metadatas[idx]["file_path"],
                language=metadatas[idx]["language"],
                content=documents[idx],
                score=distances[idx],
            )
        )

    return search_results