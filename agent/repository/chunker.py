from langchain_text_splitters import RecursiveCharacterTextSplitter
from models import RepositoryFile, CodeChunk


splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)


def chunk_file(file: RepositoryFile) -> list[CodeChunk]:

    chunks = splitter.split_text(file.content)

    results = []

    for idx, chunk in enumerate(chunks):

        results.append(
            CodeChunk(
                chunk_id=f"{file.path}:{idx}",
                file_path=file.path,
                language=file.language,
                start_line=0,
                end_line=0,
                content=chunk,
            )
        )

    return results


def chunk_repository(files: list[RepositoryFile],) -> list[CodeChunk]:
    all_chunks = []

    for file in files:
        all_chunks.extend(chunk_file(file))

    return all_chunks