"""Zip a repository's working copy for download.

Built on demand into a temp file that is deleted once streamed: nothing is stored, so there is no
object storage, no cleanup job, and no per-dyno state on Heroku.
"""
import os
import re
import tempfile
import zipfile
from typing import IO, Tuple

# Never part of a download. Narrower than the indexer's IGNORE_DIRS: `lib`, `build` and `dist` can be
# real source in a user's project, so they are kept.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".next"}
MAX_ZIP_SOURCE_BYTES = 100 * 1024 * 1024        # total size of the files before compression
_SPOOL_BYTES = 8 * 1024 * 1024                  # stay in memory below this, spill to disk above
_ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template")


class RepoZipEmpty(Exception):
    """Nothing to put in the zip."""


class RepoZipTooLarge(Exception):
    """The project is over MAX_ZIP_SOURCE_BYTES."""


def _is_secret_env_file(name: str) -> bool:
    n = name.lower()
    return (n == ".env" or n.startswith(".env.")) and not n.endswith(_ENV_TEMPLATE_SUFFIXES)


def zip_filename(repo_name: str) -> str:
    """`<repo name>.zip` limited to characters safe in a header and on every filesystem."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", repo_name or "").strip("-.")
    return f"{safe or 'repository'}.zip"


def build_repo_zip(root: str, max_bytes: int = MAX_ZIP_SOURCE_BYTES) -> Tuple[IO[bytes], int]:
    """Zip everything under `root` into a temp file; returns (file rewound to 0, size in bytes).

    Skips SKIP_DIRS, secret `.env` files, symlinks, and anything that resolves outside `root`.
    Raises RepoZipEmpty / RepoZipTooLarge. The caller closes the file.
    """
    real_root = os.path.realpath(root)
    out = tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES)
    total = count = 0
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirs, names in os.walk(real_root):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d)))
                for name in sorted(names):
                    full = os.path.join(dirpath, name)
                    if _is_secret_env_file(name) or os.path.islink(full) or not os.path.isfile(full):
                        continue
                    if os.path.commonpath([real_root, os.path.realpath(full)]) != real_root:
                        continue
                    total += os.path.getsize(full)
                    if total > max_bytes:
                        raise RepoZipTooLarge(f"project is larger than {max_bytes} bytes")
                    zf.write(full, os.path.relpath(full, real_root).replace(os.sep, "/"))
                    count += 1
        if not count:
            raise RepoZipEmpty("no files to download")
        size = out.tell()
        out.seek(0)
        return out, size
    except BaseException:
        out.close()
        raise
