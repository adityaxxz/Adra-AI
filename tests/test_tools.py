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


def test_original_capture_records_the_pre_run_content_first_write_wins(project):
    (project / "a.py").write_text("old a", encoding="utf-8")
    T.begin_original_capture()
    try:
        T.write_file.invoke({"path": "a.py", "content": "mid"})
        T.write_file.invoke({"path": "a.py", "content": "new"})       # second write must not overwrite the original
        T.write_file.invoke({"path": r"sub\new.py", "content": "x"})  # a file that didn't exist
    finally:
        captured = T.end_original_capture()
    assert captured == {"a.py": "old a", "sub/new.py": None}


def test_original_capture_skips_unreadable_files_and_is_off_by_default(project):
    (project / "bin.dat").write_bytes(b"\xff\xfe\x00\x80")
    T.begin_original_capture()
    T.write_file.invoke({"path": "bin.dat", "content": "text"})
    assert T.end_original_capture() == {}
    # not capturing: writes still work and nothing is recorded
    T.write_file.invoke({"path": "plain.py", "content": "y"})
    assert T.end_original_capture() == {}


FILES = ["index.html", "script.js", "style.css", "src/app.py", "app.py"]


def test_closest_existing_path_snaps_a_typo_onto_the_one_file_it_misspells():
    assert T.closest_existing_path("style.cc", FILES) == "style.css"
    assert T.closest_existing_path("src/app.pyy", FILES) == "src/app.py"   # same directory only


def test_closest_existing_path_leaves_real_and_genuinely_new_files_alone():
    assert T.closest_existing_path("style.css", FILES) is None       # already exists
    assert T.closest_existing_path("utils.py", FILES) is None        # nothing similar
    assert T.closest_existing_path("lib/style.cc", FILES) is None    # similar name, wrong directory


def test_closest_existing_path_refuses_to_guess_between_two_candidates():
    assert T.closest_existing_path("main.pyy", ["main.py", "main.pyi"]) is None


# ------------------------------------------------------------ line endings / rollback / per-run root

def test_write_file_keeps_the_files_existing_line_endings(project):
    (project / "crlf.txt").write_bytes(b"a\r\nb\r\n")
    (project / "lf.txt").write_bytes(b"a\nb\n")
    for name in ("crlf.txt", "lf.txt", "new.txt"):
        T.write_file.invoke({"path": name, "content": "x\ny\n"})
    assert (project / "crlf.txt").read_bytes() == b"x\r\ny\r\n"
    assert (project / "lf.txt").read_bytes() == b"x\ny\n"     # no platform-style CRLF stamped on an LF file
    assert (project / "new.txt").read_bytes() == b"x\ny\n"


def test_restore_originals_puts_everything_back_and_prunes_the_folders_it_created(project):
    (project / "keep.py").write_bytes(b"old\r\nmore\r\n")
    T.begin_original_capture()
    T.write_file.invoke({"path": "keep.py", "content": "new\nlines\n"})
    T.write_file.invoke({"path": "pkg/deep/created.py", "content": "x"})
    T.restore_originals()
    T.end_original_capture()
    assert (project / "keep.py").read_bytes() == b"old\r\nmore\r\n"
    assert not (project / "pkg").exists()          # the empty folders the run made are gone too
    assert project.exists()                         # ...but never the root


def test_project_root_is_per_run_not_process_wide(tmp_path):
    # Production bug: a request starting another run called set_project_root() on a process global,
    # repointing an edit that was already writing, so it wrote into the wrong repo.
    import threading
    seen, a_ready, b_set = {}, threading.Event(), threading.Event()

    def run(name, signal_first=None, wait_for=None):
        (tmp_path / name).mkdir()
        T.set_project_root(str(tmp_path / name))
        if signal_first: signal_first.set()
        if wait_for: wait_for.wait(5)
        T.write_file.invoke({"path": "f.txt", "content": name})
        seen[name] = T.get_project_root().name

    a = threading.Thread(target=run, args=("a", a_ready, b_set))
    b = threading.Thread(target=lambda: (a_ready.wait(5), run("b"), b_set.set()))
    a.start(); b.start(); a.join(); b.join()
    assert seen == {"a": "a", "b": "b"}
    assert (tmp_path / "a" / "f.txt").read_text() == "a" and (tmp_path / "b" / "f.txt").read_text() == "b"
