"""Pipeline-level tests with every LLM / vector-store call stubbed.

These pin the behaviours that were broken in production: state replacement
between LangGraph nodes, the integrator rewriting files it never reviewed, and
editing mode planning through a greenfield schema.
"""
import json

import pytest

from agent import graph as G
from agent import tools as T
from agent.repository.models import SearchResult
from agent.state import (
    Architect, CoderOutput, EditPlan, File, FileEdit, FileUpdate,
    IntegrationResult, Plan, TaskPlan,
)


@pytest.fixture
def project(tmp_path):
    T.set_project_root(str(tmp_path))
    yield tmp_path
    T.set_project_root(None)


def _hit(content="CTX_MARKER"):
    return SearchResult(chunk_id="c", file_path="helper.py", language="python", content=content, score=0.9)


class RecordingLLM:
    """Stands in for `structured_invoke`; records every prompt + session id per schema."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = {}

    def __call__(self, schema, prompt, **kw):
        self.calls.setdefault(schema.__name__, []).append({"prompt": prompt, "session_id": kw.get("session_id")})
        return self.respond(schema)


def _edit_repo(project):
    (project / ".git").mkdir()
    (project / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (project / "main.py").write_text("def old(): pass")
    (project / "unrelated.py").write_text("KEEP ME")


def _editing_llm():
    def respond(schema):
        if schema is EditPlan:
            return EditPlan(summary="Change main", edits=[FileEdit(filepath="main.py", change_description="edit it")])
        if schema is CoderOutput:
            return CoderOutput(content="def new(): pass")
        if schema is IntegrationResult:
            return IntegrationResult(updates=[
                FileUpdate(filepath="main.py", content="FIXED"),
                FileUpdate(filepath="unrelated.py", content="CLOBBERED"),
                FileUpdate(filepath="../escape.py", content="ESCAPED"),
            ])
        raise AssertionError(f"unexpected schema {schema}")
    return RecordingLLM(respond)


def _run_editing(project, monkeypatch, llm):
    monkeypatch.setattr(G, "structured_invoke", llm)
    monkeypatch.setattr(G, "search_repository", lambda *a, **k: [_hit("CTX_MARKER")])
    return G.repository_editing_agent.invoke(
        {"user_prompt": "edit it", "repo_path": str(project), "collection_name": "c", "session_id": "sess-1"},
        {"recursion_limit": 30},
    )


# ----------------------------------------------------------------- state propagation

def test_carry_overlays_updates_and_preserves_everything_else():
    out = G._carry({"a": 1, "b": 2}, b=3, c=4)
    assert out == {"a": 1, "b": 3, "c": 4}


def test_editing_state_survives_every_node(project, monkeypatch):
    """StateGraph(dict) REPLACES state with each node's return value. A node that
    returned only its own keys used to drop session_id / coder_state / context."""
    _edit_repo(project)
    llm = _editing_llm()
    result = _run_editing(project, monkeypatch, llm)

    assert "coder_state" in result, "coder_state lost -> edited_files would always be {}"
    assert result["session_id"] == "sess-1"
    for schema in ("EditPlan", "CoderOutput", "IntegrationResult"):
        assert [c["session_id"] for c in llm.calls[schema]] == ["sess-1"], f"session_id lost before {schema}"
    assert "CTX_MARKER" in llm.calls["CoderOutput"][0]["prompt"], "retrieved_context lost before the coder"


# ------------------------------------------------------------- integrator scoping

def test_integrator_only_reviews_and_rewrites_files_the_coder_changed(project, monkeypatch):
    _edit_repo(project)
    llm = _editing_llm()
    result = _run_editing(project, monkeypatch, llm)

    prompt = llm.calls["IntegrationResult"][0]["prompt"]
    assert "main.py" in prompt
    assert "KEEP ME" not in prompt, "unchanged repo files must not be shown as reviewable"
    assert "CTX_MARKER" in prompt, "retrieved code should reach the integrator as read-only reference"

    assert (project / "main.py").read_text() == "FIXED"
    assert (project / "unrelated.py").read_text() == "KEEP ME", "integrator clobbered a file it never reviewed"
    assert not (project.parent / "escape.py").exists(), "path traversal write was not blocked"
    assert result["integration_fixes"] == 1, "discarded updates must not be counted as fixes"


# ------------------------------------------------------------------- edit planner

def test_edit_planner_is_grounded_in_the_real_file_listing(project, monkeypatch):
    _edit_repo(project)
    llm = _editing_llm()
    _run_editing(project, monkeypatch, llm)

    prompt = llm.calls["EditPlan"][0]["prompt"]
    assert "main.py" in prompt and "unrelated.py" in prompt
    assert ".git" not in prompt
    assert "CTX_MARKER" in prompt


def test_edit_plan_is_adapted_into_the_task_plan_the_coder_consumes(project, monkeypatch):
    _edit_repo(project)
    result = _run_editing(project, monkeypatch, _editing_llm())
    task_plan = result["coder_state"].task_plan
    assert [(s.filepath, s.task_description) for s in task_plan.steps] == [("main.py", "edit it")]
    assert G._plan_summary(task_plan) == "Change main"


def test_editing_graph_does_not_use_the_greenfield_planner_or_architect():
    nodes = set(G.repository_editing_graph.nodes)
    assert "edit_planner" in nodes
    assert not {"planner", "architect"} & nodes


def test_plan_summary_falls_back_for_generation_plans_and_unknowns():
    assert G._plan_summary(TaskPlan(steps=[])) == "Unknown project"
    tp = TaskPlan(steps=[])
    tp.plan = Plan(name="App", description="does things", techstack="python", features=[], files=[])
    assert G._plan_summary(tp) == "App — does things (python)"


# ----------------------------------------------------------------------- generation

def test_generation_pipeline_still_runs_planner_architect_coder_integrator(project, monkeypatch):
    def respond(schema):
        if schema is Plan:
            return Plan(name="Hello", description="d", techstack="python", features=["f"],
                        files=[File(path="hello.py", purpose="p")])
        if schema is TaskPlan:
            return TaskPlan(steps=[Architect(filepath="hello.py", task_description="print hi")])
        if schema is CoderOutput:
            return CoderOutput(content="print('hi')")
        if schema is IntegrationResult:
            return IntegrationResult(updates=[])
        raise AssertionError(schema)

    llm = RecordingLLM(respond)
    monkeypatch.setattr(G, "structured_invoke", llm)
    result = G.project_generation_agent.invoke({"user_prompt": "make hello", "session_id": "gen-1"}, {"recursion_limit": 30})

    assert (project / "hello.py").read_text() == "print('hi')"
    assert list(llm.calls) == ["Plan", "TaskPlan", "CoderOutput", "IntegrationResult"]
    assert all(c["session_id"] == "gen-1" for calls in llm.calls.values() for c in calls)
    assert G._plan_summary(result["coder_state"].task_plan).startswith("Hello")


def test_planner_prompt_has_no_repository_instructions():
    # generation has no repo; the old prompt told the model to "use the repository context" anyway
    from agent.prompts import planner_prompt
    assert "repository" not in planner_prompt("build a todo app").lower()


# ------------------------------------------------------------------------------- QA

def test_question_answering_returns_answer_and_keeps_state(monkeypatch):
    monkeypatch.setattr(G, "search_repository", lambda *a, **k: [_hit("def add(a, b): return a + b")])
    seen = {}

    def fake_simple(prompt, **kw):
        seen["prompt"], seen["session_id"] = prompt, kw.get("session_id")
        return "add() adds two numbers"

    monkeypatch.setattr(G, "simple_invoke", fake_simple)
    result = G.question_answering_agent.invoke(
        {"user_prompt": "what does add do?", "repo_path": ".", "collection_name": "c", "session_id": "qa-1"},
        {"recursion_limit": 10},
    )
    assert result["answer"] == "add() adds two numbers"
    assert result["session_id"] == "qa-1" and seen["session_id"] == "qa-1"
    assert "def add" in seen["prompt"]


def test_retrieval_failure_degrades_to_empty_context_instead_of_failing_the_run(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(G, "search_repository", boom)
    monkeypatch.setattr(G, "simple_invoke", lambda prompt, **kw: "I could not see the code")
    result = G.question_answering_agent.invoke(
        {"user_prompt": "q", "repo_path": ".", "collection_name": "c", "session_id": "s"}, {"recursion_limit": 10}
    )
    assert result["answer"] == "I could not see the code"
    assert result["retrieved_context"] == ""
