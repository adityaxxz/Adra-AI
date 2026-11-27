"""Two-level incremental indexing (file hash, then chunk hash), against an
in-memory stand-in for Qdrant so no embeddings or network are involved.

Mirrors the scenarios verified live against real Qdrant + embeddings.
"""
import pytest

from agent.repository import service as S
from agent.repository.chunker import chunk_repository
from agent.repository.scanner import scan_repository

V1 = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n"


class FakeStore:
    """Just enough of vector_store.py, keyed by chunk_id like the real point ids."""

    def __init__(self):
        self.points = {}      # chunk_id -> payload
        self.embedded = 0     # how many chunks were "embedded" (the expensive step)

    def install(self, monkeypatch):
        for name in ("set_active_collection",):
            monkeypatch.setattr(S, name, lambda *a, **k: None)
        monkeypatch.setattr(S, "clear_collection", lambda *a, **k: self.points.clear())
        monkeypatch.setattr(S, "index_chunks", self.index_chunks)
        monkeypatch.setattr(S, "get_file_hashes", lambda *a, **k: {p["file_path"]: p["file_hash"] for p in self.points.values()})
        monkeypatch.setattr(S, "get_files_in_collection", lambda *a, **k: {p["file_path"] for p in self.points.values()})
        monkeypatch.setattr(S, "get_chunk_hashes_for_file",
                            lambda fp, *a, **k: {cid: p["chunk_hash"] for cid, p in self.points.items() if p["file_path"] == fp})
        monkeypatch.setattr(S, "delete_chunk_by_id", lambda cid, *a, **k: self.points.pop(cid, None))
        monkeypatch.setattr(S, "delete_file_chunks", self.delete_file_chunks)
        monkeypatch.setattr(S, "set_file_hash", self.set_file_hash)

    def set_file_hash(self, chunk_ids, file_hash, collection_name=None):
        for cid in chunk_ids:
            self.points[cid]["file_hash"] = file_hash

    def index_chunks(self, chunks, collection_name=None):
        for c in chunks:
            self.embedded += 1
            self.points[c.chunk_id] = {
                "file_path": c.file_path, "file_hash": c.file_hash, "chunk_hash": c.chunk_hash, "content": c.content,
            }

    def delete_file_chunks(self, file_path, collection_name=None):
        ids = [cid for cid, p in self.points.items() if p["file_path"] == file_path]
        for cid in ids:
            del self.points[cid]
        return len(ids)


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    s.install(monkeypatch)
    return s


def _fresh_chunk_count(root):
    return len(chunk_repository(scan_repository(str(root))))


def _write(root, name, content):
    (root / name).write_text(content, encoding="utf-8", newline="\n")


def test_full_index_stores_every_chunk(make_repo, store):
    root = make_repo({"calc.py": V1, "helpers.py": 'def greet(n):\n    return "hi " + n\n'})
    stats = S.index_repository(str(root), "c", reset=True)
    assert len(store.points) == stats.chunks_created == _fresh_chunk_count(root)


def test_reindex_with_no_changes_embeds_nothing(make_repo, store):
    root = make_repo({"calc.py": V1, "helpers.py": "X = 1\n"})
    S.index_repository(str(root), "c", reset=True)
    embedded = store.embedded
    stats = S.index_repository(str(root), "c")
    assert stats.files_skipped == 2 and stats.files_indexed == 0 and stats.chunks_created == 0
    assert store.embedded == embedded


def test_whitespace_only_edit_re_embeds_zero_chunks(make_repo, store):
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    embedded = store.embedded

    _write(root, "calc.py", V1.replace("return a + b", "return a + b   ").rstrip("\n") + "\n\n\n")
    stats = S.index_repository(str(root), "c")

    assert stats.files_indexed == 1, "the file hash changed, so the file is diffed"
    assert stats.chunks_created == 0 and store.embedded == embedded, "but no chunk's normalised hash changed"
    assert stats.chunks_skipped > 0


def test_editing_one_function_re_embeds_only_the_affected_chunks(make_repo, store):
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    total = len(store.points)

    _write(root, "calc.py", V1.replace("return a * b", "return a * b  # scaled"))
    stats = S.index_repository(str(root), "c")

    assert 0 < stats.chunks_created < total
    assert stats.chunks_skipped > 0
    assert len(store.points) == _fresh_chunk_count(root), "no duplicate or orphaned points"
    assert any("scaled" in p["content"] for p in store.points.values())
    assert not any("return a * b\n" in p["content"] and "scaled" not in p["content"] and "def mul" in p["content"]
                   for p in store.points.values()), "stale copy of the edited function is still stored"


def test_deleting_a_function_removes_its_chunk(make_repo, store):
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)

    _write(root, "calc.py", V1.replace("def sub(a, b):\n    return a - b\n\n\n", ""))
    S.index_repository(str(root), "c")

    assert len(store.points) == _fresh_chunk_count(root)
    assert not any("def sub" in p["content"] for p in store.points.values())


def test_deleting_a_file_removes_its_chunks(make_repo, store):
    root = make_repo({"calc.py": V1, "helpers.py": "X = 1\n"})
    S.index_repository(str(root), "c", reset=True)

    (root / "helpers.py").unlink()
    stats = S.index_repository(str(root), "c")

    assert stats.files_deleted == 1
    assert {p["file_path"] for p in store.points.values()} == {"calc.py"}


def test_a_new_file_is_indexed_without_touching_existing_chunks(make_repo, store):
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    embedded = store.embedded

    _write(root, "extra.py", "Y = 2\n\n\ndef f():\n    return Y\n")
    stats = S.index_repository(str(root), "c")

    assert stats.files_skipped == 1 and stats.files_indexed == 1
    assert store.embedded - embedded == stats.chunks_created > 0
    assert len(store.points) == _fresh_chunk_count(root)


def test_chunks_from_before_chunk_hashing_are_re_embedded_once_then_stable(make_repo, store):
    """Points indexed before chunk hashes existed have an empty chunk_hash in
    their payload, so the first real change to that file re-embeds all of its chunks."""
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    for p in store.points.values():
        p["chunk_hash"] = ""                                   # legacy payloads

    _write(root, "calc.py", V1.replace("return a * b", "return a * b  # v2"))
    stats = S.index_repository(str(root), "c")
    assert stats.chunks_created == len(store.points) == _fresh_chunk_count(root)

    again = S.index_repository(str(root), "c")
    assert again.chunks_created == 0 and again.files_skipped == 1


def test_after_a_partial_update_every_chunk_carries_the_new_file_hash(make_repo, store):
    """Kept chunks used to keep the old file_hash. With mixed hashes, which one the index reported for the file was
    arbitrary, so reverting the file (a rejected edit) could be skipped while the edited chunk stayed stale."""
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    _write(root, "calc.py", V1.replace("return a * b", "return a * b  # scaled"))
    S.index_repository(str(root), "c")
    current = scan_repository(str(root))[0].file_hash
    assert {p["file_hash"] for p in store.points.values()} == {current}


def test_reverting_an_edit_restores_the_original_chunks(make_repo, store):
    """The reject path: edit, refresh, restore the original, refresh -> the index holds the original code again."""
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    original = {cid: p["content"] for cid, p in store.points.items()}
    _write(root, "calc.py", V1.replace("return a * b", "return a * b  # scaled"))
    S.index_repository(str(root), "c")
    _write(root, "calc.py", V1)
    S.index_repository(str(root), "c")
    assert {cid: p["content"] for cid, p in store.points.items()} == original


def test_a_file_whose_chunks_disagree_on_its_hash_is_reported_as_changed(monkeypatch):
    """Collections written before the fix can hold mixed hashes; report "" so the file is always diffed."""
    from types import SimpleNamespace as NS
    from agent.repository import vector_store as V

    pts = [NS(payload={"file_path": "a.css", "file_hash": "old"}), NS(payload={"file_path": "a.css", "file_hash": "new"}),
           NS(payload={"file_path": "b.css", "file_hash": "same"}), NS(payload={"file_path": "b.css", "file_hash": "same"})]
    monkeypatch.setattr(V, "client", NS(scroll=lambda **k: (pts, None)))
    assert V.get_file_hashes("c") == {"a.css": "", "b.css": "same"}


def test_empty_repository_clears_the_index(make_repo, store):
    root = make_repo({"calc.py": V1})
    S.index_repository(str(root), "c", reset=True)
    (root / "calc.py").unlink()
    S.index_repository(str(root), "c")
    assert store.points == {}
