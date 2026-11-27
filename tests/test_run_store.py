import pytest
from sqlalchemy import func, select

import backend.main as M
from backend import run_store
from backend.db_models import AgentRun, RunStep, Session, SessionMode, User

METRICS = {
    "session_id": "s", "llm_calls": 5, "input_tokens": 1200, "output_tokens": 800,
    "total_tokens": 2000, "cost_usd": 0.00123, "latency_ms": 5400.5, "retries": 1,
    "per_agent": {
        "edit_planner": {"calls": 1, "input_tokens": 400, "output_tokens": 100, "latency_ms": 900.0},
        "coder": {"calls": 3, "input_tokens": 700, "output_tokens": 600, "latency_ms": 4000.0},
        "integrator": {"calls": 1, "input_tokens": 100, "output_tokens": 100, "latency_ms": 500.5},
    },
}


def _build(task_result, mode="editing"):
    return run_store.build_agent_run(session_id="s1", mode=mode, prompt="add a thing", task_result=task_result,
                                     provider="groq", model="openai/gpt-oss-120b")


# ----------------------------------------------------------------- building (no DB)

def test_a_successful_run_carries_its_metrics_and_per_agent_steps():
    run = _build({"success": True, "metrics": METRICS, "result": {"integration_fixes": 2}})
    assert (run.status, run.error_message) == ("success", None)
    assert (run.llm_calls, run.input_tokens, run.output_tokens, run.retries) == (5, 1200, 800, 1)
    assert run.cost_usd == pytest.approx(0.00123) and run.latency_ms == pytest.approx(5400.5)
    assert run.integration_fixes == 2
    assert {s.agent: s.calls for s in run.steps} == {"edit_planner": 1, "coder": 3, "integrator": 1}
    assert sum(s.input_tokens for s in run.steps) == run.input_tokens


def test_generation_reports_integration_fixes_at_the_top_level():
    assert _build({"success": True, "metrics": METRICS, "integration_fixes": 3}, "generation").integration_fixes == 3


def test_a_failed_run_keeps_the_error_and_whatever_it_spent_before_dying():
    run = _build({"success": False, "error": "429 rate limited", "metrics": {**METRICS, "llm_calls": 2}})
    assert run.status == "failure" and run.error_message == "429 rate limited"
    assert run.llm_calls == 2 and run.input_tokens == 1200


def test_a_run_that_died_before_any_llm_call_has_zeroes_not_errors():
    run = _build({"success": False, "error": "clone failed"})
    assert run.status == "failure" and run.steps == []
    assert (run.llm_calls, run.input_tokens, run.cost_usd) == (0, 0, 0.0)


def test_a_run_records_the_versions_of_the_prompts_its_mode_used():
    from agent.prompts import PROMPT_VERSIONS as V
    assert _build({"success": True}, "question_answering").prompt_versions == {"explainer": V["explainer"]}
    assert _build({"success": True}, "editing").prompt_versions == {k: V[k] for k in ("edit_planner", "coder", "integrator")}
    assert set(_build({"success": True}, "generation").prompt_versions) == {"planner", "architect", "coder", "integrator"}


def test_qa_runs_have_no_integration_fixes():
    assert _build({"success": True, "metrics": METRICS}, "question_answering").integration_fixes == 0


# -------------------------------------------------------- failure metrics (no DB)

async def test_a_pipeline_that_dies_mid_run_still_reports_what_it_spent(monkeypatch):
    """RunMetrics lives in the executor thread's context; the failure result used to
    carry nothing back, so a failed run's tokens/cost/retries vanished."""
    from backend import background_tasks as BT

    class DyingGraph:
        def invoke(self, state, config):
            from agent import observability as O
            O.record_call("openai/gpt-oss-120b", "groq", {"input_tokens": 50, "output_tokens": 10}, 7.0, agent="explainer")
            raise RuntimeError("provider exploded")

    monkeypatch.setattr(BT, "question_answering_agent", DyingGraph())
    out = await BT.BackgroundTaskManager(max_workers=1).execute_question_answering(
        "sess-x", "q", ".", "coll", recursion_limit=5
    )
    assert out["success"] is False and "provider exploded" in out["error"]
    assert out["metrics"]["llm_calls"] == 1 and out["metrics"]["input_tokens"] == 50


# ------------------------------------------------------------------- DB (integration)

pytestmark_db = pytest.mark.integration


async def _seed_session(db, sid="s1"):
    if not (await db.execute(select(User).where(User.id == "u1"))).scalar_one_or_none():
        db.add(User(id="u1", email="u1@example.com", name="u1", provider="google"))
    db.add(Session(id=sid, user_id="u1", mode=SessionMode.EDITING, messages=[], is_active=False))
    await db.commit()


@pytestmark_db
async def test_record_agent_run_saves_the_run_and_its_steps(db_session_maker):
    async with db_session_maker() as db:
        await _seed_session(db)
        saved = await run_store.record_agent_run(
            db, session_id="s1", mode="editing", prompt="add a thing",
            task_result={"success": True, "metrics": METRICS, "result": {"integration_fixes": 1}},
            provider="groq", model="openai/gpt-oss-120b",
        )
    assert saved is not None
    async with db_session_maker() as db:
        run = (await db.execute(select(AgentRun))).scalar_one()
        steps = (await db.execute(select(RunStep).where(RunStep.run_id == run.id))).scalars().all()
    assert (run.session_id, run.mode, run.status, run.provider) == ("s1", "editing", "success", "groq")
    assert run.input_tokens == 1200 and run.cost_usd == pytest.approx(0.00123) and run.integration_fixes == 1
    assert run.created_at is not None
    assert sorted(s.agent for s in steps) == ["coder", "edit_planner", "integrator"]
    assert set(run.prompt_versions) == {"edit_planner", "coder", "integrator"}, "versions survive the database round trip"


@pytestmark_db
async def test_recording_never_raises_even_when_the_insert_fails(db_session_maker):
    async with db_session_maker() as db:
        # session "ghost" does not exist -> foreign key violation
        out = await run_store.record_agent_run(
            db, session_id="ghost", mode="editing", prompt="p", task_result={"success": True, "metrics": METRICS},
            provider="groq", model="m",
        )
        assert out is None
        # and the session is still usable afterwards (the failed transaction was rolled back)
        assert (await db.execute(select(func.count()).select_from(AgentRun))).scalar_one() == 0


@pytestmark_db
async def test_deleting_a_session_deletes_its_runs_and_steps(db_session_maker):
    """delete_repository deletes sessions; user prompts must go with them, and the
    delete must not trip over the new foreign keys."""
    async with db_session_maker() as db:
        await _seed_session(db)
        await run_store.record_agent_run(db, session_id="s1", mode="editing", prompt="secret prompt",
                                         task_result={"success": True, "metrics": METRICS}, provider="groq", model="m")
    async with db_session_maker() as db:
        session = (await db.execute(select(Session).where(Session.id == "s1"))).scalar_one()
        await db.delete(session)
        await db.commit()
    async with db_session_maker() as db:
        assert (await db.execute(select(func.count()).select_from(AgentRun))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(RunStep))).scalar_one() == 0


@pytestmark_db
async def test_background_task_records_the_run_and_still_finalises_the_session(db_session_maker, monkeypatch):
    monkeypatch.setattr(M, "async_session", db_session_maker)
    async with db_session_maker() as db:
        await _seed_session(db, "s-qa")
        s = (await db.execute(select(Session).where(Session.id == "s-qa"))).scalar_one()
        s.is_active = True
        await db.commit()

    async def fake_qa(**kwargs):
        return {"success": True, "answer": "42", "metrics": METRICS, "result": {}, "task_id": "t"}

    monkeypatch.setattr(M.task_manager, "execute_question_answering", fake_qa)
    await M._run_generation_task(
        mode=SessionMode.QUESTION_ANSWERING, session_id="s-qa", prompt="what is the answer?", project_root="./x",
        project_id=None, repository_id="r", repo_path=".", collection_name="c", recursion_limit=5,
    )
    async with db_session_maker() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.session_id == "s-qa"))).scalar_one()
        session = (await db.execute(select(Session).where(Session.id == "s-qa"))).scalar_one()
    assert run.mode == "question_answering" and run.user_prompt == "what is the answer?" and run.llm_calls == 5
    assert session.is_active is False and session.result["answer"] == "42"


async def _edit_run(db_session_maker, monkeypatch, sid, task_result, index):
    monkeypatch.setattr(M, "async_session", db_session_maker)
    monkeypatch.setattr(M, "index_repository", index)
    async with db_session_maker() as db:
        await _seed_session(db, sid)

    async def fake_edit(**kwargs):
        return {"metrics": METRICS, "task_id": "t", **task_result}

    monkeypatch.setattr(M.task_manager, "execute_repository_editing", fake_edit)
    await M._run_generation_task(
        mode=SessionMode.EDITING, session_id=sid, prompt="change it", project_root="./x",
        project_id=None, repository_id=None, repo_path="/repo", collection_name="repo_c", recursion_limit=5,
    )
    async with db_session_maker() as db:
        return (await db.execute(select(Session).where(Session.id == sid))).scalar_one()


@pytestmark_db
async def test_an_edit_run_refreshes_the_search_index_after_writing(db_session_maker, monkeypatch):
    """Live bug: Ask mode answered from the pre-edit code because nothing re-indexed after an edit."""
    calls = []
    await _edit_run(db_session_maker, monkeypatch, "s-e1", {"success": True, "edited_files": {"style.css": "x"}},
                    lambda path, coll: calls.append((path, coll)))
    assert calls == [("/repo", "repo_c")]


@pytestmark_db
async def test_a_failed_or_empty_edit_run_does_not_reindex(db_session_maker, monkeypatch):
    calls = []
    await _edit_run(db_session_maker, monkeypatch, "s-e2", {"success": False, "error": "boom"}, lambda *a: calls.append(a))
    await _edit_run(db_session_maker, monkeypatch, "s-e3", {"success": True, "edited_files": {}}, lambda *a: calls.append(a))
    assert calls == []


@pytestmark_db
async def test_a_failed_index_refresh_cannot_break_the_edit_run(db_session_maker, monkeypatch):
    def explode(*a):
        raise RuntimeError("qdrant down")

    session = await _edit_run(db_session_maker, monkeypatch, "s-e4", {"success": True, "edited_files": {"a": "b"}}, explode)
    assert session.is_active is False and session.result["success"] is True


@pytestmark_db
async def test_a_recording_failure_cannot_break_the_user_facing_run(db_session_maker, monkeypatch):
    monkeypatch.setattr(M, "async_session", db_session_maker)
    async with db_session_maker() as db:
        await _seed_session(db, "s-qa2")
        s = (await db.execute(select(Session).where(Session.id == "s-qa2"))).scalar_one()
        s.is_active = True
        await db.commit()

    async def fake_qa(**kwargs):
        return {"success": True, "answer": "still delivered", "metrics": METRICS, "result": {}, "task_id": "t"}

    def explode(*a, **k):
        raise RuntimeError("telemetry bug")

    monkeypatch.setattr(M.task_manager, "execute_question_answering", fake_qa)
    monkeypatch.setattr(run_store, "build_agent_run", explode)
    await M._run_generation_task(
        mode=SessionMode.QUESTION_ANSWERING, session_id="s-qa2", prompt="q", project_root="./x",
        project_id=None, repository_id="r", repo_path=".", collection_name="c", recursion_limit=5,
    )
    async with db_session_maker() as db:
        session = (await db.execute(select(Session).where(Session.id == "s-qa2"))).scalar_one()
        assert (await db.execute(select(func.count()).select_from(AgentRun))).scalar_one() == 0
    assert session.is_active is False and session.result["answer"] == "still delivered"
