import pytest

from agent import tools as T


@pytest.fixture
def project(tmp_path):
    T.set_project_root(str(tmp_path))
    yield tmp_path
    T.set_project_root(None)


def _populate(root):
    for rel, content in {
        ".git/HEAD": "ref: refs/heads/main",
        ".git/objects/ab/deadbeef": "binary-ish",
        "node_modules/react/index.js": "var a=1;",
        ".venv/lib/site.py": "# venv",
        "__pycache__/x.pyc": "\x00",
        "main.py": "print(1)",
        "requirements.txt": "fastapi",
        "Dockerfile": "FROM python:3.11",
        "src/app.py": "def f(): pass",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_list_project_paths_skips_noise_dirs_but_keeps_non_code_files(project):
    _populate(project)
    paths = T.list_project_paths()
    # Regression: `.git/**` sorts before source, so it used to eat the whole context budget.
    assert paths == ["Dockerfile", "main.py", "requirements.txt", "src/app.py"]


def test_ignore_list_only_applies_below_the_project_root(tmp_path):
    # The root itself may live in a directory called "build"/"lib"; that must not hide everything.
    root = tmp_path / "build" / "proj"
    root.mkdir(parents=True)
    (root / "a.py").write_text("x", encoding="utf-8")
    T.set_project_root(str(root))
    try:
        assert T.list_project_paths() == ["a.py"]
    finally:
        T.set_project_root(None)


def test_read_selected_project_files_returns_only_requested_in_order(project):
    _populate(project)
    out = T.read_selected_project_files(["src/app.py", "main.py", "missing.py"])
    assert out.index("=== src/app.py ===") < out.index("=== main.py ===")
    assert "missing.py" not in out
    assert "requirements.txt" not in out and "Dockerfile" not in out


def test_read_selected_project_files_with_nothing_readable(project):
    assert T.read_selected_project_files(["nope.py"]) == "(no files to review)"


def test_sibling_context_excludes_the_target_and_ignored_dirs(project):
    _populate(project)
    ctx = T.read_sibling_files_context("main.py")
    assert "=== main.py ===" not in ctx
    assert "=== src/app.py ===" in ctx
    assert ".git" not in ctx and "node_modules" not in ctx


def test_safe_path_rejects_traversal(project):
    with pytest.raises(ValueError):
        T.safe_path_for_project("../outside.py")


def test_write_file_tool_cannot_escape_the_root(project):
    with pytest.raises(ValueError):
        T.write_file.invoke({"path": "../escape.py", "content": "x"})
    assert not (project.parent / "escape.py").exists()
