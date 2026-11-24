import contextvars
import difflib
import logging
import pathlib
import subprocess
from typing import Tuple, Optional

from langchain_core.tools import tool

from agent.repository.scanner import IGNORE_DIRS

logger = logging.getLogger(__name__)

# Default project root for project generation mode
DEFAULT_PROJECT_ROOT = pathlib.Path.cwd() / "generated_projects"

# The folder the running agent reads and writes. A contextvar rather than a module
# global: runs share one process, and with a global a request that started another
# run repointed an edit that was already writing, so it changed the wrong folder.
# Each worker sets its own root; the value follows the run into LangGraph's threads.
_project_root: contextvars.ContextVar = contextvars.ContextVar("project_root", default=DEFAULT_PROJECT_ROOT)


def set_project_root(path: Optional[str] = None) -> None:
    """Set the project root for file operations. If None, resets to default."""
    _project_root.set(DEFAULT_PROJECT_ROOT if path is None else pathlib.Path(path).resolve())


def get_project_root() -> pathlib.Path:
    """Get the current project root."""
    return _project_root.get()


def safe_path_for_project(path: str) -> pathlib.Path:
    root = get_project_root()
    p = (root / path).resolve()
    if root.resolve() not in p.parents and root.resolve() != p.parent and root.resolve() != p:
        raise ValueError("Attempt to write outside project root")
    return p


def write_text_keeping_endings(p: pathlib.Path, text: str) -> None:
    """Write `text`, using the line-ending style the file already has (CRLF stays CRLF, otherwise LF).

    Python's text mode would instead stamp the *platform's* style on every write, turning a whole LF
    file into CRLF on Windows (or the reverse), which shows up as every line changed in git."""
    crlf = p.exists() and b"\r\n" in p.read_bytes()
    text = text.replace("\r\n", "\n")
    p.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def remove_file_and_empty_dirs(p: pathlib.Path, root: pathlib.Path) -> None:
    """Delete `p`, then any parent folders it leaves empty (stopping at `root`)."""
    p.unlink(missing_ok=True)
    parent = p.parent
    while parent != root and root in parent.parents and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


# Pre-edit content of files written during an editing run, for review/revert:
# {path: original text, or None if the file didn't exist}. None = not capturing.
_originals: contextvars.ContextVar = contextvars.ContextVar("original_files", default=None)


def begin_original_capture() -> None:
    _originals.set({})


def end_original_capture() -> dict:
    """Stop capturing and return what was captured."""
    captured = _originals.get() or {}
    _originals.set(None)
    return captured


def restore_originals() -> None:
    """Undo this run's writes: put back every captured file and delete the ones the run created.

    For a run that fails part-way, so the repo isn't left half-edited with nothing to review."""
    root = get_project_root()
    for key, original in (_originals.get() or {}).items():
        p = safe_path_for_project(key)
        if original is None:
            remove_file_and_empty_dirs(p, root.resolve())
        else:
            write_text_keeping_endings(p, original)


@tool
def write_file(path: str, content: str) -> str:
    """Writes content to a file at the specified path within the project root."""
    p = safe_path_for_project(path)
    originals = _originals.get()
    if originals is not None:
        key = path.replace("\\", "/")
        if key not in originals:  # first write wins: the state before this run
            if not p.exists():
                originals[key] = None
            else:
                try:
                    # Universal newlines, like every other read in the app, so diffs aren't all CRLF noise.
                    originals[key] = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    pass  # binary/unreadable: can't be reverted, so don't offer it
    p.parent.mkdir(parents=True, exist_ok=True)
    write_text_keeping_endings(p, content)
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
    return str(get_project_root())


@tool
def list_files(directory: str = ".") -> str:
    """Lists all files in the specified directory within the project root."""
    p = safe_path_for_project(directory)
    if not p.is_dir():
        return f"ERROR: {p} is not a directory"
    files = [str(f.relative_to(get_project_root())) for f in p.glob("**/*") if f.is_file()]
    return "\n".join(files) if files else "No files found."

@tool
def run_cmd(cmd: str, cwd: str = None, timeout: int = 30) -> Tuple[int, str, str]:
    """Runs a shell command in the specified directory and returns the result."""
    cwd_dir = safe_path_for_project(cwd) if cwd else get_project_root()
    res = subprocess.run(cmd, shell=True, cwd=str(cwd_dir), capture_output=True, text=True, timeout=timeout)
    return res.returncode, res.stdout, res.stderr


def init_project_root():
    root = get_project_root()
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def list_project_paths() -> list[str]:
    """List project files the agents are allowed to see.

    Skips IGNORE_DIRS (`.git`, `node_modules`, `.venv`, ...) — in repository
    editing mode the project root is a real checkout, and `.git/**` sorts ahead of
    source alphabetically, so without this filter git internals and vendored
    deps consume the whole context budget before any real code is reached.
    Extension is deliberately NOT filtered: generated projects legitimately
    contain requirements.txt / Dockerfile / *.yml that the agents must see.
    """
    root = get_project_root()
    if not root.exists():
        return []
    return sorted(
        str(f.relative_to(root)).replace("\\", "/")
        for f in root.glob("**/*")
        if f.is_file() and not any(part in IGNORE_DIRS for part in f.relative_to(root).parts)
    )


def closest_existing_path(path: str, existing: list[str], cutoff: float = 0.8) -> Optional[str]:
    """The one existing file `path` is almost certainly a misspelling of, else None.

    Only a near-identical name in the same directory counts (`style.cc` ->
    `style.css`), and only when exactly one file qualifies; anything else is left
    alone so a genuinely new file is never redirected onto an unrelated one.
    """
    norm = path.replace("\\", "/")
    if norm in existing:
        return None
    directory, _, name = norm.rpartition("/")
    matches = [
        e for e in existing
        if e.rpartition("/")[0] == directory
        and difflib.SequenceMatcher(None, name, e.rpartition("/")[2]).ratio() >= cutoff
    ]
    return matches[0] if len(matches) == 1 else None


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
            logger.warning(f"read_sibling_files_context: skipping unreadable file {rel_path!r}: {e}")
            continue
    return "\n\n".join(parts) if parts else "(no other project files yet)"


def read_selected_project_files(paths: list[str]) -> str:
    """Return contents of only the given project files, in the order given."""
    parts: list[str] = []
    for rel_path in paths:
        try:
            content = read_file.invoke({"path": rel_path})
        except Exception as e:
            logger.warning(f"read_selected_project_files: skipping unreadable file {rel_path!r}: {e}")
            continue
        if content.strip() and not content.startswith("[Binary file skipped"):
            parts.append(f"=== {rel_path} ===\n{content}")
    return "\n\n".join(parts) if parts else "(no files to review)"