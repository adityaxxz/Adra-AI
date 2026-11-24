from backend.edit_review import apply_review


def _run(tmp_path, **extra):
    """A repo after an editing run: main.py modified, new.py created."""
    (tmp_path / "main.py").write_text("new main", encoding="utf-8")
    (tmp_path / "new.py").write_text("brand new", encoding="utf-8")
    result = {
        "edited_files": {"main.py": "new main", "new.py": "brand new"},
        "original_files": {"main.py": "old main", "new.py": None},
    }
    result.update(extra)
    return result


def test_reject_restores_the_original_and_deletes_files_the_run_created(tmp_path):
    out = apply_review(str(tmp_path), _run(tmp_path), [], ["main.py", "new.py"], {})
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "old main"
    assert not (tmp_path / "new.py").exists()
    assert out["review"] == {"main.py": "rejected", "new.py": "rejected"}
    assert out["files"] == {"main.py": "old main", "new.py": None}  # what Repository.files must now hold
    assert out["conflicts"] == []


def test_accept_keeps_the_file_and_marks_it(tmp_path):
    out = apply_review(str(tmp_path), _run(tmp_path), ["main.py"], [], {})
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "new main"
    assert out["review"] == {"main.py": "accepted"} and out["files"] == {}


def test_accept_with_hand_edited_content_writes_it(tmp_path):
    out = apply_review(str(tmp_path), _run(tmp_path), ["main.py"], [], {"main.py": "tweaked"})
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "tweaked"
    assert out["files"] == {"main.py": "tweaked"}


def test_a_decided_file_cannot_be_decided_again(tmp_path):
    result = _run(tmp_path)
    first = apply_review(str(tmp_path), result, ["main.py"], [], {})
    result["edit_review"] = first["review"]
    # rejecting after accepting must not revert the file
    again = apply_review(str(tmp_path), result, [], ["main.py"], {})
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "new main"
    assert again["review"]["main.py"] == "accepted" and again["files"] == {}


def test_a_file_changed_since_the_run_is_left_alone_and_reported(tmp_path):
    result = _run(tmp_path)
    (tmp_path / "main.py").write_text("a later run's work", encoding="utf-8")
    out = apply_review(str(tmp_path), result, [], ["main.py"], {})
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "a later run's work"
    assert out["conflicts"] == ["main.py"] and "main.py" not in out["review"]


def test_paths_outside_the_run_or_the_repo_are_ignored(tmp_path):
    (tmp_path.parent / "outside.txt").write_text("keep", encoding="utf-8")
    result = _run(tmp_path)
    result["edited_files"]["../outside.txt"] = "keep"
    result["original_files"]["../outside.txt"] = "pwned"
    out = apply_review(str(tmp_path), result, [], ["../outside.txt", "not_in_run.py"], {})
    assert (tmp_path.parent / "outside.txt").read_text(encoding="utf-8") == "keep"
    assert out["review"] == {} and out["files"] == {}


def test_reject_without_a_captured_original_is_a_conflict_not_a_deletion(tmp_path):
    result = _run(tmp_path)
    del result["original_files"]["main.py"]
    out = apply_review(str(tmp_path), result, [], ["main.py"], {})
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "new main"
    assert out["conflicts"] == ["main.py"]


def test_rejecting_restores_crlf_files_as_crlf_and_prunes_folders_a_new_file_created(tmp_path):
    (tmp_path / "win.py").write_bytes(b"edited\r\nline\r\n")              # the agent kept the file's CRLF style
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "new.py").write_text("brand new", encoding="utf-8")
    result = {
        "edited_files": {"win.py": "edited\nline\n", "pkg/new.py": "brand new"},   # read back with universal newlines
        "original_files": {"win.py": "original\nline\n", "pkg/new.py": None},
    }
    out = apply_review(str(tmp_path), result, [], ["win.py", "pkg/new.py"], {})
    assert out["conflicts"] == []
    assert (tmp_path / "win.py").read_bytes() == b"original\r\nline\r\n"
    assert not (tmp_path / "pkg").exists() and tmp_path.exists()
