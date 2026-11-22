import json

from agent.repository import service as S
from agent.repository.models import RepositoryFile


def test_snapshot_contains_only_indexable_files_with_forward_slash_keys(make_repo):
    root = make_repo({
        "main.py": "print(1)",
        "src/app.py": "def f(): pass",
        "README.md": "# hi",
        "logo.png": "not text",
        "node_modules/x/index.js": "var a;",
        ".git/config": "[core]",
    })
    snap = S.snapshot_repo_files(str(root))
    assert set(snap) == {"main.py", "src/app.py", "README.md"}
    assert snap["src/app.py"] == "def f(): pass"


def test_snapshot_normalises_windows_separators(monkeypatch):
    # edited_files from the editing pipeline use "/", scan_repository uses the OS
    # separator; mismatched keys would duplicate files when the two are merged.
    monkeypatch.setattr(
        S, "scan_repository",
        lambda p: [RepositoryFile(path="src\\app.py", language="python", content="x", file_hash="h")],
    )
    assert S.snapshot_repo_files("ignored") == {"src/app.py": "x"}


def test_snapshot_is_json_serialisable(make_repo):
    # it is stored in a JSON column
    json.dumps(S.snapshot_repo_files(str(make_repo({"a.py": "x = 1"}))))


def test_rehydrate_recreates_a_wiped_repo(tmp_path):
    target = tmp_path / "uploaded_repos" / "r1"           # does not exist: dyno disk was wiped
    files = {"main.py": "print(1)", "src/app.py": "def f(): pass"}
    out = S.ensure_repo_on_disk(str(target), files, "r1")
    assert out == str(target)
    assert (target / "main.py").read_text(encoding="utf-8") == "print(1)"
    assert (target / "src" / "app.py").read_text(encoding="utf-8") == "def f(): pass"


def test_rehydrate_never_overwrites_a_populated_directory(tmp_path):
    (tmp_path / "main.py").write_text("LOCAL EDIT", encoding="utf-8")
    out = S.ensure_repo_on_disk(str(tmp_path), {"main.py": "SNAPSHOT"}, "r1")
    assert out == str(tmp_path)
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "LOCAL EDIT"


def test_rehydrate_without_a_snapshot_is_a_noop(tmp_path):
    missing = str(tmp_path / "gone")
    assert S.ensure_repo_on_disk(missing, None, "r1") == missing
    assert S.ensure_repo_on_disk(missing, {}, "r1") == missing
    assert S.ensure_repo_on_disk(None, None, "r1") is None
    assert not (tmp_path / "gone").exists()


def test_rehydrate_blocks_path_traversal_and_skips_unreadable_files(tmp_path):
    target = tmp_path / "repo"
    S.ensure_repo_on_disk(str(target), {"ok.py": "x", "../evil.py": "bad", "unreadable.py": None}, "r1")
    assert (target / "ok.py").exists()
    assert not (tmp_path / "evil.py").exists()
    assert not (target / "unreadable.py").exists()


def test_rehydrate_with_no_local_path_uses_a_fresh_temp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = S.ensure_repo_on_disk(None, {"a.py": "x"}, "repo-id")
    assert out.replace("\\", "/").endswith("temp_repos/repo-id")
    assert (tmp_path / "temp_repos" / "repo-id" / "a.py").exists()
