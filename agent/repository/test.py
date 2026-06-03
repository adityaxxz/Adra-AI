from scanner import scan_repository
from chunker import chunk_repository
from vector_store import index_chunks, clear_collection
from retriever import retrieve

files = scan_repository(r"A:\AI-LLM\Adra-AI\projects using integrator node\generated_project_blog_api_using_fastapi_and_sqlite")

chunks = chunk_repository(files)

# print(f"Files: {len(files)}")
# print(f"Chunks: {len(chunks)}")

# print(chunks[0].content)

chunks = chunk_repository(files)

clear_collection()

index_chunks(chunks)

results = retrieve(
    "How does the db implemented?"
)

for result in results:
    print()
    print(result.file_path)
    print("-" * 50)
    print(result.content[:300])