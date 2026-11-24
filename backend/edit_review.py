"""Accept / reject the files an editing run changed.

The agent writes straight to disk, so reviewing is write-first: a rejected file
is restored to the content it had before the run (`original_files`, captured by
`agent.tools.write_file`), and an accepted one is simply marked as kept.
"""
from pathlib import Path
from typing import Dict, List, Optional

from agent.tools import remove_file_and_empty_dirs, write_text_keeping_endings

PENDING, ACCEPTED, REJECTED = "pending", "accepted", "rejected"


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return None


def apply_review(
    repo_root: str,
    result: dict,
    accept: List[str],
    reject: List[str],
    edited: Dict[str, str],
) -> dict:
    """Apply the user's decisions for one editing run to the files on disk.

    `result` is the run's stored task result. Only files still pending can be
    decided, and a file is skipped (reported in `conflicts`) if it no longer
    holds what the run wrote - a later run or a manual edit got there first, and
    restoring the old original would silently destroy that work.

    Returns {"review": {path: status}, "files": {path: new content or None to
    drop}, "conflicts": [path]}; `files` is what to write back to
    `Repository.files`, which mirrors the disk.
    """
    root = Path(repo_root).resolve()
    edited_files = result.get("edited_files") or {}
    originals = result.get("original_files") or {}
    review = dict(result.get("edit_review") or {})
    files: Dict[str, Optional[str]] = {}
    conflicts: List[str] = []

    decisions = [(p, ACCEPTED) for p in accept] + [(p, REJECTED) for p in reject]
    for path, decision in decisions:
        if path not in edited_files or review.get(path, PENDING) != PENDING:
            continue
        target = (root / path).resolve()
        if root not in target.parents:
            continue
        if _read(target) != edited_files[path]:
            conflicts.append(path)
            continue

        if decision == ACCEPTED:
            if path in edited and edited[path] != edited_files[path]:
                write_text_keeping_endings(target, edited[path])
                files[path] = edited[path]
        else:
            if path not in originals:
                conflicts.append(path)
                continue
            if originals[path] is None:
                remove_file_and_empty_dirs(target, root)
                files[path] = None
            else:
                write_text_keeping_endings(target, originals[path])
                files[path] = originals[path]
        review[path] = decision

    return {"review": review, "files": files, "conflicts": conflicts}
