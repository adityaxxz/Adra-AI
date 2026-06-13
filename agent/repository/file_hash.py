import hashlib


def generate_file_hash(content: str) -> str:
    """Generate SHA256 hash for file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


# def generate_file_hash_from_path(file_path: str) -> str:
#     """Generate SHA256 hash for file by reading from path."""
#     try:
#         with open(file_path, 'rb') as f:
#             return hashlib.sha256(f.read()).hexdigest()
#     except Exception:
#         return ""
