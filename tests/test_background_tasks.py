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
