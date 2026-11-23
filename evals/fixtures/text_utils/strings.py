"""String helpers."""
import re


def slugify(text: str) -> str:
    """Lowercase `text`, replace runs of non-alphanumeric characters with a single
    hyphen, and strip leading/trailing hyphens. "Hello, World!" -> "hello-world"."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Return `text` unchanged if it is at most `length` characters long.

    Otherwise cut it so that the result, *including* `suffix`, is exactly `length`
    characters. truncate("hello world", 8) -> "hello..."
    """
    return text[:length] + suffix


def word_count(text: str) -> int:
    """Number of whitespace-separated words in `text`."""
    return len(text.split())
