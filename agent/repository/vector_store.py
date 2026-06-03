import chromadb
from models import CodeChunk
from embeddings import embed_text


client = chromadb.PersistentClient(path="./chroma_db")

def get_collection():
    return client.get_or_create_collection(
        name="repo_chunks"
    )


def index_chunks(chunks: list[CodeChunk]) -> None:
    collection = get_collection()

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

            }
        )

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def clear_collection() -> None:
    global collection

    client.delete_collection("repo_chunks")

    collection = client.get_or_create_collection(
        name="repo_chunks"
    )