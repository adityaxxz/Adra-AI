import json

from agent.state import Architect, CoderState, Plan, TaskPlan
from backend import background_tasks as BT


def _coder_state(*paths):
    tp = TaskPlan(steps=[Architect(filepath=p, task_description="t") for p in paths])
    tp.plan = Plan(name="n", description="d", techstack="py", features=[], files=[])
    return CoderState(task_plan=tp, current_step_idx=len(paths))


def test_serializable_result_strips_pydantic_state_so_the_json_column_accepts_it():
    graph_state = {
        "user_prompt": "x", "session_id": "s", "repo_path": "r", "collection_name": "c",
        "retrieved_context": "lots of retrieved code",
        "plan": Plan(name="n", description="d", techstack="py", features=[], files=[]),
        "task_plan": _coder_state("a.py").task_plan,
        "coder_state": _coder_state("a.py"),
        "integration_fixes": 2, "status": "DONE",
    }
    json.dumps({"success": True, "result": BT._serializable_result(graph_state)})  # must not raise
    safe = BT._serializable_result(graph_state)
    assert safe["integration_fixes"] == 2 and safe["session_id"] == "s"
    assert not {"plan", "task_plan", "coder_state", "retrieved_context"} & set(safe)


def test_serializable_result_tolerates_non_dicts():
    assert BT._serializable_result(None) == {}


def test_collect_edited_files_reads_the_files_the_coder_wrote(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "main.py").write_text("edited main", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text("edited app", encoding="utf-8")
    (tmp_path / "untouched.py").write_text("old", encoding="utf-8")

    mgr = BT.BackgroundTaskManager(max_workers=1)
    edited = mgr._collect_edited_files({"coder_state": _coder_state("main.py", "src/app.py")}, str(tmp_path))
    assert edited == {"main.py": "edited main", "src/app.py": "edited app"}


def test_collect_edited_files_is_empty_when_state_was_lost(tmp_path):
    # the pre-fix symptom: the final graph state had no coder_state at all
    mgr = BT.BackgroundTaskManager(max_workers=1)
    assert mgr._collect_edited_files({"integration_fixes": 0}, str(tmp_path)) == {}


# --------------------------------------------------- editing run: review payload, rollback, per-run root

def test_only_changed_drops_files_the_run_rewrote_to_what_they_already_held():
    edited = {"same.py": "x", "changed.py": "new", "created.py": "", "unknown.py": "y"}
    originals = {"same.py": "x", "changed.py": "old", "created.py": None}
    assert BT._only_changed(edited, originals) == {"changed.py": "new", "created.py": "", "unknown.py": "y"}


def test_editing_message_reports_what_changed_what_the_planner_said_and_what_was_skipped():
    assert BT._editing_message(["a.py", "b.py"], None, []) == "✅ Done! Edited 2 file(s): a.py, b.py"
    msg = BT._editing_message([], "That's a question, so nothing to change.", [])
    assert msg == "No files were changed.\n\nThat's a question, so nothing to change."
    assert "Skipped (binary or too large to edit safely): logo.png" in BT._editing_message(["a.py"], "s", ["logo.png"])


class _FakeAgent:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.root_seen = None

    def invoke(self, state, config):
        from agent import tools as T
        self.root_seen = T.get_project_root()
        return self.behaviour(T)


def _run_editing_worker(monkeypatch, repo, behaviour):
    mgr = BT.BackgroundTaskManager(max_workers=1)
    agent = _FakeAgent(behaviour)
    monkeypatch.setattr(BT, "repository_editing_agent", agent)
    return mgr, agent


def test_a_failed_editing_run_rolls_back_the_files_it_had_already_written(tmp_path, monkeypatch):
    # Production gap: a run dying after the first of several writes left the repo half-edited, unreported.
    import pytest
    (tmp_path / "a.py").write_text("original")

    def behaviour(T):
        T.write_file.invoke({"path": "a.py", "content": "half done"})
        T.write_file.invoke({"path": "pkg/new.py", "content": "x"})
        raise RuntimeError("429 quota exceeded")

    mgr, _ = _run_editing_worker(monkeypatch, tmp_path, behaviour)
    with pytest.raises(RuntimeError):
        mgr._run_repository_editing_agent("edit", str(tmp_path), "c", 10, "sess")
    assert (tmp_path / "a.py").read_text() == "original"
    assert not (tmp_path / "pkg").exists()


def test_the_editing_worker_uses_its_own_root_and_returns_the_originals(tmp_path, monkeypatch):
    from agent import tools as T
    (tmp_path / "a.py").write_text("old")
    mgr, agent = _run_editing_worker(
        monkeypatch, tmp_path,
        lambda T: T.write_file.invoke({"path": "a.py", "content": "new"}) and {"coder_state": None},
    )
    result = mgr._run_repository_editing_agent("edit", str(tmp_path), "c", 10, "sess")
    assert agent.root_seen == tmp_path.resolve()
    assert result["_original_files"] == {"a.py": "old"}
    assert T.get_project_root() == T.DEFAULT_PROJECT_ROOT, "the worker leaked its root into the pool thread"
