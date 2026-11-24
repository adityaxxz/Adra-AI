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


def _run_editing(project, monkeypatch, llm, prompt="edit it"):
    monkeypatch.setattr(G, "structured_invoke", llm)
    monkeypatch.setattr(G, "search_repository", lambda *a, **k: [_hit("CTX_MARKER")])
    return G.repository_editing_agent.invoke(
        {"user_prompt": prompt, "repo_path": str(project), "collection_name": "c", "session_id": "sess-1"},
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


def _typo_llm(filepath):
    def respond(schema):
        if schema is EditPlan:
            return EditPlan(summary="Comment", edits=[FileEdit(filepath=filepath, change_description="add a comment")])
        if schema is CoderOutput:
            return CoderOutput(content="# commented")
        if schema is IntegrationResult:
            return IntegrationResult(updates=[])
        raise AssertionError(f"unexpected schema {schema}")
    return RecordingLLM(respond)


def test_a_misspelt_filename_edits_the_real_file_instead_of_creating_a_new_one(project, monkeypatch):
    # Production bug: "...top of style.cc" created a brand-new style.cc next to style.css.
    (project / "style.css").write_text("body {}")
    result = _run_editing(project, monkeypatch, _typo_llm("style.cc"), prompt="Add a comment at the top of style.cc")
    assert [s.filepath for s in result["coder_state"].task_plan.steps] == ["style.css"]
    assert not (project / "style.cc").exists()
    assert (project / "style.css").read_text() == "# commented"


def test_asking_for_a_new_file_is_not_redirected_onto_a_similar_one(project, monkeypatch):
    (project / "style.css").write_text("body {}")
    result = _run_editing(project, monkeypatch, _typo_llm("style.cc"), prompt="Create a new file style.cc")
    assert [s.filepath for s in result["coder_state"].task_plan.steps] == ["style.cc"]
    assert (project / "style.cc").exists() and (project / "style.css").read_text() == "body {}"


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


# ------------------------------------------------- whole-file safety, skipping, scoping

def _plan_llm(paths, coder="# commented", updates=None):
    def respond(schema):
        if schema is EditPlan:
            return EditPlan(summary="s", edits=[FileEdit(filepath=p, change_description="d") for p in paths])
        if schema is CoderOutput:
            return CoderOutput(content=coder)
        if schema is IntegrationResult:
            return IntegrationResult(updates=updates or [])
        raise AssertionError(f"unexpected schema {schema}")
    return RecordingLLM(respond)


def test_the_coder_sees_the_whole_file_it_is_asked_to_rewrite(project, monkeypatch):
    # Production bug: the file was cut to 10k chars, then the model's "complete file" was the cut-off text.
    (project / "big.py").write_text("x = 1\n" * 5000 + "TAIL_MARKER = 1\n")
    llm = _plan_llm(["big.py"])
    _run_editing(project, monkeypatch, llm)
    prompt = llm.calls["CoderOutput"][0]["prompt"]
    assert "TAIL_MARKER" in prompt and "truncated" not in prompt


def test_a_file_too_big_to_show_in_full_is_left_untouched_and_reported(project, monkeypatch):
    monkeypatch.setattr(G, "MAX_EDIT_FILE_CHARS", 100)
    (project / "huge.py").write_text("y = 2\n" * 100)
    (project / "small.py").write_text("z = 1\n")
    llm = _plan_llm(["huge.py", "small.py"])
    result = _run_editing(project, monkeypatch, llm)
    assert (project / "huge.py").read_text() == "y = 2\n" * 100
    assert (project / "small.py").read_text() == "# commented\n"
    assert result["skipped_files"] == ["huge.py"] and len(llm.calls["CoderOutput"]) == 1
    assert "huge.py" not in llm.calls["IntegrationResult"][0]["prompt"]


def test_binary_files_are_never_rewritten_as_text(project, monkeypatch):
    blob = b"\x89PNG\r\n\x1a\n\x00\x00binary"   # read_file's latin-1 fallback would happily "decode" this
    (project / "logo.png").write_bytes(blob)
    result = _run_editing(project, monkeypatch, _plan_llm(["logo.png"]))
    assert (project / "logo.png").read_bytes() == blob and result["skipped_files"] == ["logo.png"]


def test_integrator_only_updates_files_it_was_shown_in_full(project, monkeypatch):
    # An integrator update replaces the whole file, so a file it only saw part of must not be updated.
    monkeypatch.setattr(G, "MAX_INTEGRATOR_CHARS", 30)
    (project / "a.py").write_text("a = 1\n")
    (project / "b.py").write_text("b = 2\n")
    llm = _plan_llm(["a.py", "b.py"], coder="# " + "c" * 20,
                    updates=[FileUpdate(filepath="a.py", content="A FIXED"), FileUpdate(filepath="b.py", content="B CLOBBERED")])
    result = _run_editing(project, monkeypatch, llm)
    prompt = llm.calls["IntegrationResult"][0]["prompt"]
    assert "=== a.py ===" in prompt and "=== b.py ===" not in prompt
    assert (project / "a.py").read_text() == "A FIXED\n"
    assert (project / "b.py").read_text() == "# " + "c" * 20 + "\n"
    assert result["integration_fixes"] == 1


def test_a_request_that_needs_no_edits_changes_nothing_and_skips_the_other_agents(project, monkeypatch):
    (project / "main.py").write_text("keep")
    llm = _plan_llm([])
    result = _run_editing(project, monkeypatch, llm, prompt="what does this do?")
    assert "CoderOutput" not in llm.calls and "IntegrationResult" not in llm.calls
    assert result["coder_state"].task_plan.steps == [] and (project / "main.py").read_text() == "keep"


def test_the_edit_planner_is_shown_every_file_of_a_large_repo(project, monkeypatch):
    # Production risk: a 4k-char listing hid whole directories, so the planner invented paths for them.
    for i in range(400):
        (project / f"module_{i:03d}.py").write_text("")
    (project / "zzz_last.py").write_text("")
    llm = _plan_llm([])
    _run_editing(project, monkeypatch, llm)
    assert "zzz_last.py" in llm.calls["EditPlan"][0]["prompt"]


def test_two_plan_entries_for_one_file_become_one_step_carrying_both_instructions(project, monkeypatch):
    (project / "a.py").write_text("a = 1\n")
    def respond(schema):
        if schema is EditPlan:
            return EditPlan(summary="s", edits=[FileEdit(filepath="a.py", change_description="FIRST"),
                                                FileEdit(filepath="a.py", change_description="SECOND")])
        if schema is CoderOutput:
            return CoderOutput(content="# done")
        return IntegrationResult(updates=[])
    llm = RecordingLLM(respond)
    result = _run_editing(project, monkeypatch, llm)
    (step,) = result["coder_state"].task_plan.steps
    assert "FIRST" in step.task_description and "SECOND" in step.task_description
    assert len(llm.calls["CoderOutput"]) == 1


def test_the_coder_is_told_to_preserve_what_it_isnt_asked_to_change_only_for_existing_files(project, monkeypatch):
    (project / "old.py").write_text("keep = 1\n")
    llm = _plan_llm(["old.py", "fresh.py"])
    _run_editing(project, monkeypatch, llm)
    old_prompt, fresh_prompt = (c["prompt"] for c in llm.calls["CoderOutput"])
    assert "Change ONLY what the Task requires" in old_prompt
    assert "Change ONLY what the Task requires" not in fresh_prompt


def test_concurrent_edits_to_different_repos_each_write_to_their_own_repo(tmp_path, monkeypatch):
    # Production bug: the project root was a process global, so a second run repointed the first mid-flight.
    import threading
    barrier = threading.Barrier(2)

    def respond(schema):
        if schema is EditPlan:
            return EditPlan(summary="s", edits=[FileEdit(filepath="main.py", change_description="d")])
        if schema is CoderOutput:
            barrier.wait(10)   # both runs are now mid-flight, each with its own root
            return CoderOutput(content="# edited")
        return IntegrationResult(updates=[])

    monkeypatch.setattr(G, "structured_invoke", RecordingLLM(respond))
    monkeypatch.setattr(G, "search_repository", lambda *a, **k: [])
    errors = []

    def run(root):
        try:
            T.set_project_root(str(root))
            G.repository_editing_agent.invoke(
                {"user_prompt": "edit it", "repo_path": str(root), "collection_name": "c", "session_id": "s"},
                {"recursion_limit": 30},
            )
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    roots = []
    for name in ("repo_a", "repo_b"):
        root = tmp_path / name
        root.mkdir()
        (root / "main.py").write_text("# original")
        roots.append(root)
    threads = [threading.Thread(target=run, args=(r,)) for r in roots]
    [t.start() for t in threads]; [t.join(30) for t in threads]
    assert not errors, errors
    assert [(r / "main.py").read_text() for r in roots] == ["# edited", "# edited"]


def test_a_file_the_model_returns_with_every_quote_escaped_is_written_clean(project, monkeypatch):
    # Production bug: "add a comment to indx.html" came back as lang=\"en\" on 17 lines and was written as is.
    (project / "index.html").write_text('<html lang="en">\n<body class="x"></body>\n</html>\n')
    escaped = '<!-- page -->\n<html lang=\\"en\\">\n<body class=\\"x\\"></body>\n</html>\n'
    _run_editing(project, monkeypatch, _plan_llm(["index.html"], coder=escaped))
    assert (project / "index.html").read_text() == '<!-- page -->\n<html lang="en">\n<body class="x"></body>\n</html>\n'


def test_an_edit_keeps_a_files_final_newline_and_does_not_invent_one(project, monkeypatch):
    # The model's output is .strip()ed, which used to drop the final newline of every edited file.
    (project / "with_nl.py").write_text("a = 1\n")
    (project / "no_nl.py").write_text("b = 2")
    _run_editing(project, monkeypatch, _plan_llm(["with_nl.py", "no_nl.py"], coder="x = 0"))
    assert (project / "with_nl.py").read_text() == "x = 0\n"
    assert (project / "no_nl.py").read_text() == "x = 0"
