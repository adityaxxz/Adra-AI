import pathlib
import subprocess
from typing import Tuple, Optional

from langchain_core.tools import tool

# Default project root for project generation mode
DEFAULT_PROJECT_ROOT = pathlib.Path.cwd() / "generated_projects"
# Current active project root (can be changed for repository editing mode)
PROJECT_ROOT = DEFAULT_PROJECT_ROOT


def set_project_root(path: Optional[str] = None) -> None:
    """Set the project root for file operations. If None, resets to default."""
    global PROJECT_ROOT
    if path is None:
        PROJECT_ROOT = DEFAULT_PROJECT_ROOT
    else:
        PROJECT_ROOT = pathlib.Path(path).resolve()


def get_project_root() -> pathlib.Path:
    """Get the current project root."""
    return PROJECT_ROOT


def safe_path_for_project(path: str) -> pathlib.Path:
    p = (PROJECT_ROOT / path).resolve()
    if PROJECT_ROOT.resolve() not in p.parents and PROJECT_ROOT.resolve() != p.parent and PROJECT_ROOT.resolve() != p:
        raise ValueError("Attempt to write outside project root")
    return p


@tool
def write_file(path: str, content: str) -> str:
    """Writes content to a file at the specified path within the project root."""
    p = safe_path_for_project(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return f"WROTE:{p}"


@tool
def read_file(path: str) -> str:
    """Reads content from a file at the specified path within the project root."""
    p = safe_path_for_project(path)
    if not p.exists():
        return ""
    
    # Try different encodings to handle various file types
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    
    for encoding in encodings:
        try:
            with open(p, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # If all encodings fail, it's likely a binary file
    return f"[Binary file skipped: {path}]"


@tool
def get_current_directory() -> str:
    """Returns the current working directory."""
    return str(PROJECT_ROOT)


@tool
def list_files(directory: str = ".") -> str:
    """Lists all files in the specified directory within the project root."""
    p = safe_path_for_project(directory)
    if not p.is_dir():
        return f"ERROR: {p} is not a directory"
    files = [str(f.relative_to(PROJECT_ROOT)) for f in p.glob("**/*") if f.is_file()]
    return "\n".join(files) if files else "No files found."

@tool
def run_cmd(cmd: str, cwd: str = None, timeout: int = 30) -> Tuple[int, str, str]:
    """Runs a shell command in the specified directory and returns the result."""
    cwd_dir = safe_path_for_project(cwd) if cwd else PROJECT_ROOT
    res = subprocess.run(cmd, shell=True, cwd=str(cwd_dir), capture_output=True, text=True, timeout=timeout)
    return res.returncode, res.stdout, res.stderr


def init_project_root():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    return str(PROJECT_ROOT)


def list_project_paths() -> list[str]:
    if not PROJECT_ROOT.exists():
        return []
    return sorted(
        str(f.relative_to(PROJECT_ROOT)).replace("\\", "/")
        for f in PROJECT_ROOT.glob("**/*")
        if f.is_file()
    )


def read_sibling_files_context(exclude_path: str) -> str:
    """Return contents of all other project files for cross-file integration."""
    exclude = exclude_path.replace("\\", "/")
    parts: list[str] = []
    for rel_path in list_project_paths():
        if rel_path == exclude:
            continue
        try:
            content = read_file.invoke({"path": rel_path})
            if content.strip() and not content.startswith("[Binary file skipped"):
                parts.append(f"=== {rel_path} ===\n{content}")
        except Exception as e:
            # Skip files that can't be read
            continue
    return "\n\n".join(parts) if parts else "(no other project files yet)"


def read_all_project_files() -> str:
    parts: list[str] = []
    for rel_path in list_project_paths():
        content = read_file.invoke({"path": rel_path})
        if content.strip():
            parts.append(f"=== {rel_path} ===\n{content}")
    return "\n\n".join(parts) if parts else "(empty project)"