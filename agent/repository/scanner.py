from pathlib import Path
from models import RepositoryFile


SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
    ".json": "json",
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
}


def scan_repository(repo_path: str) -> list[RepositoryFile]:
    files: list[RepositoryFile] = []

    root = Path(repo_path)

    for file_path in root.rglob("*"):

        if not file_path.is_file():
            continue

        if any(part in IGNORE_DIRS for part in file_path.parts):
            continue

        suffix = file_path.suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            continue

        try:
            content = file_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception:
            continue

        files.append(
            RepositoryFile(
                path=str(file_path.relative_to(root)),
                language=SUPPORTED_EXTENSIONS[suffix],
                content=content,
            )
        )

    return files


# if __name__ == "__main__":

#     files = scan_repository(
#         r"A:\AI-LLM\Adra-AI\projects using integrator node\generated_project_blog_api_using_fastapi_and_sqlite"
#     )

#     print(f"Found {len(files)} files")

#     for file in files[:5]:
#         print(file.path)