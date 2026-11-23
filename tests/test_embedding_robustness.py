"""Two ways indexing used to fall over on ordinary repositories (found 2026-11-23 while measuring retrieval):

1. An empty file (e.g. an empty __init__.py) became an empty chunk; the Gemini embeddings API rejects empty text
   (400 "contains an empty Part"), so indexing the whole repository raised.
2. Indexing embeds one chunk per call; the free tier allows 100 calls a minute, and embed_text re-raised the 429.
"""
import pytest

from agent import rate_limit as RL
from agent.repository import embeddings as E
from agent.repository import service as S
from agent.repository.chunker import chunk_repository
from agent.repository.scanner import scan_repository

CALC = "def add(a, b):\n    return a + b\n"
EMBED_429 = ("429 RESOURCE_EXHAUSTED. {'error': {'message': 'Embed content requests per minute limit exceeded on Free Tier. "
             "Please retry in 12.5s.'}}")
EMBED_DAILY_429 = ("429 RESOURCE_EXHAUSTED. {'error': {'message': 'Embed content requests per day limit exceeded on Free Tier. "
                   "Please retry in 20h25m14s.'}}")


# ------------------------------------------------------------------ empty files

class StrictEmbeddingStore:
    """Stands in for the vector store but refuses blank text exactly like the Gemini embeddings API does."""

    def __init__(self):
        self.points = {}

    def install(self, monkeypatch):
        monkeypatch.setattr(S, "set_active_collection", lambda *a, **k: None)
        monkeypatch.setattr(S, "clear_collection", lambda *a, **k: self.points.clear())
        monkeypatch.setattr(S, "index_chunks", self.index_chunks)
        monkeypatch.setattr(S, "get_file_hashes", lambda *a, **k: {p["file_path"]: p["file_hash"] for p in self.points.values()})
        monkeypatch.setattr(S, "get_files_in_collection", lambda *a, **k: {p["file_path"] for p in self.points.values()})
        monkeypatch.setattr(S, "get_chunk_hashes_for_file",
                            lambda fp, *a, **k: {cid: p["chunk_hash"] for cid, p in self.points.items() if p["file_path"] == fp})
        monkeypatch.setattr(S, "delete_chunk_by_id", lambda cid, *a, **k: self.points.pop(cid, None))
        monkeypatch.setattr(S, "delete_file_chunks", lambda fp, *a, **k: 0)

    def index_chunks(self, chunks, collection_name=None):
        for c in chunks:
            if not c.content.strip():
                raise RuntimeError(f"400 INVALID_ARGUMENT: EmbedContentRequest.content contains an empty Part ({c.chunk_id})")
            self.points[c.chunk_id] = {"file_path": c.file_path, "file_hash": c.file_hash, "chunk_hash": c.chunk_hash}


@pytest.fixture
def store(monkeypatch):
    s = StrictEmbeddingStore()
    s.install(monkeypatch)
    return s


def test_no_chunk_is_ever_blank(make_repo):
    root = make_repo({"pkg/__init__.py": "", "pkg/blank.py": "\n\n   \n", "pkg/calc.py": CALC})
    chunks = chunk_repository(scan_repository(str(root)))
    assert chunks and all(c.content.strip() for c in chunks)
    assert {c.file_path.replace("\\", "/") for c in chunks} == {"pkg/calc.py"}


def test_a_repo_with_empty_files_indexes_instead_of_failing(make_repo, store):
    root = make_repo({"pkg/__init__.py": "", "calc.py": CALC, "notes.md": "   \n"})
    stats = S.index_repository(str(root), "c", reset=True)
    assert stats.chunks_created > 0 and {p["file_path"].replace("\\", "/") for p in store.points.values()} == {"calc.py"}


def test_reindexing_a_repo_with_empty_files_also_works(make_repo, store):
    root = make_repo({"pkg/__init__.py": "", "calc.py": CALC})
    S.index_repository(str(root), "c", reset=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "calc.py").write_text(CALC + "\n\ndef sub(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    S.index_repository(str(root), "c")
    assert store.points and all(p["file_path"].endswith("calc.py") for p in store.points.values())


def test_a_file_that_becomes_empty_is_not_embedded(make_repo, store):
    root = make_repo({"calc.py": CALC, "other.py": "X = 1\n"})
    S.index_repository(str(root), "c", reset=True)
    (root / "other.py").write_text("", encoding="utf-8")
    S.index_repository(str(root), "c")          # must not raise on the now-empty file


# ------------------------------------------------------------- embedding rate limits

class FakeEmbeddings:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def embed_query(self, text, task_type=None):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


@pytest.fixture
def sleeps(monkeypatch):
    waited = []
    monkeypatch.setattr(RL.time, "sleep", waited.append)
    return waited


def _use(monkeypatch, outcomes):
    fake = FakeEmbeddings(outcomes)
    monkeypatch.setattr(E, "embeddings", fake)
    return fake


def test_a_per_minute_embedding_limit_is_waited_out(monkeypatch, sleeps):
    fake = _use(monkeypatch, [RuntimeError(EMBED_429), [0.1, 0.2]])
    assert E.embed_text("x = 1", task_type="RETRIEVAL_DOCUMENT") == [0.1, 0.2]
    assert fake.calls == 2 and sleeps == [pytest.approx(13.5)]


def test_indexing_a_burst_survives_repeated_limits(monkeypatch, sleeps):
    fake = _use(monkeypatch, [RuntimeError(EMBED_429)] * 3 + [[1.0]])
    assert E.embed_text("x", task_type="RETRIEVAL_DOCUMENT") == [1.0]
    assert fake.calls == 4 and len(sleeps) == 3


def test_it_gives_up_after_the_retry_budget(monkeypatch, sleeps):
    fake = _use(monkeypatch, [RuntimeError(EMBED_429)] * (E.EMBED_RATE_LIMIT_RETRIES + 1))
    with pytest.raises(RuntimeError, match="429"):
        E.embed_text("x", task_type="RETRIEVAL_DOCUMENT")
    assert fake.calls == E.EMBED_RATE_LIMIT_RETRIES + 1


def test_a_daily_embedding_quota_is_not_waited_on(monkeypatch, sleeps):
    fake = _use(monkeypatch, [RuntimeError(EMBED_DAILY_429), [1.0]])
    with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
        E.embed_text("x", task_type="RETRIEVAL_DOCUMENT")
    assert fake.calls == 1 and sleeps == []


def test_other_embedding_errors_are_not_retried(monkeypatch, sleeps):
    fake = _use(monkeypatch, [ValueError("400 INVALID_ARGUMENT"), [1.0]])
    with pytest.raises(ValueError):
        E.embed_text("x", task_type="RETRIEVAL_DOCUMENT")
    assert fake.calls == 1 and sleeps == []


# ---------------------------------------------------------------- the shared helper

def test_the_shared_helper_returns_the_value_and_raises_non_rate_errors_untouched(sleeps):
    assert RL.call_with_rate_limit_backoff(lambda: 7, retries=2, max_wait=60) == 7
    with pytest.raises(KeyError):
        RL.call_with_rate_limit_backoff(lambda: {}["x"], retries=2, max_wait=60)
    assert sleeps == []


def test_a_hint_longer_than_max_wait_is_not_waited_on(sleeps):
    def call():
        raise RuntimeError("429 rate limit. Please try again in 70s.")
    with pytest.raises(RuntimeError):
        RL.call_with_rate_limit_backoff(call, retries=3, max_wait=60)
    assert sleeps == []
