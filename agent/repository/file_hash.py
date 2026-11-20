import hashlib


def generate_file_hash(content: str) -> str:
    """Generate SHA256 hash for file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def generate_chunk_hash(content: str) -> str:
    """Generate a whitespace-normalized SHA256 hash for a chunk's content.

    Strips trailing whitespace from every line and collapses leading/trailing
    blank lines before hashing.  This makes the hash invariant to cosmetic
    edits (extra spaces, blank lines added/removed) so that chunk-level
    incremental indexing skips re-embedding chunks whose *semantic* content
    has not changed.
    """
    normalized = "\n".join(line.rstrip() for line in content.splitlines()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# def generate_file_hash_from_path(file_path: str) -> str:
#     """Generate SHA256 hash for file by reading from path."""
#     try:
#         with open(file_path, 'rb') as f:
#             return hashlib.sha256(f.read()).hexdigest()
#     except Exception:
#         return ""
