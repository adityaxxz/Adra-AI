"""§2.5 "Online evals + feedback loop": grading real runs (1 in 10 + every thumbs-down) and the admin view."""
import httpx
import pytest
from sqlalchemy import func, select

import backend.main as M
from backend import online_eval as OE
from backend import run_store
from backend.db_models import EvalResult, Repository, Session, SessionMode, User, UserRole
from evals.evaluators.outcome import Outcome

integration = pytest.mark.integration
METRICS = {"llm_calls": 1, "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0001, "latency_ms": 10.0, "retries": 0, "per_agent": {}}


class StubJudge:
    model = "stub-judge"

    def __init__(self, passed=True, explode=False):
        self.passed, self.explode, self.calls = passed, explode, []

    def _verdict(self):
        if self.explode:
            raise RuntimeError("judge exploded")
        return Outcome("judge", "judge", self.passed, "correctness=5 (stub)" if self.passed else "correctness=1 (stub)",
                       score=0.9 if self.passed else 0.2, required=True)

    def judge_answer(self, case, answer, context):
        self.calls.append(("answer", case, answer, context))
        return self._verdict()

    def judge_code(self, case, after, before=None):
        self.calls.append(("code", case, after, before))
        return self._verdict()


async def _seed(db, *, mode="question_answering", result=None, success=True, user_id="u1", session_id="s1", role=UserRole.USER):
    if not await db.get(User, user_id):
        db.add(User(id=user_id, email=f"{user_id}@example.com", name=user_id, provider="google", role=role))
    if not await db.get(Repository, "r1"):
        await db.flush()
        db.add(Repository(id="r1", user_id=user_id, name="repo", collection_name="repo_r1", provider="github"))
    db.add(Session(id=session_id, user_id=user_id, mode=SessionMode(mode), repository_id="r1", messages=[], is_active=False,
                   result=result or {}))
    await db.commit()
    run = await run_store.record_agent_run(db, session_id=session_id, mode=mode, prompt="what does it do?",
                                           task_result={"success": success, "error": None if success else "boom", "metrics": METRICS},
                                           provider="groq", model="m")
    return run.id


# ------------------------------------------------------------------ which runs get graded

def test_sampling_is_reproducible_and_takes_about_one_in_ten():
    ids = [f"run-{i}" for i in range(4000)]
    picked = [i for i in ids if OE.is_sampled(i, 0.1)]
    assert 0.08 < len(picked) / len(ids) < 0.12
    assert picked == [i for i in ids if OE.is_sampled(i, 0.1)], "the same run is always in or out"


def test_sampling_can_be_switched_off_or_made_total():
    assert not any(OE.is_sampled(f"r{i}", 0) for i in range(200))
    assert all(OE.is_sampled(f"r{i}", 1) for i in range(200))


# ------------------------------------------------------------------ grading each kind of run

@integration
async def test_a_qa_run_is_graded_on_its_answer_and_the_code_retrieval_finds(db_session_maker):
    judge, seen = StubJudge(), {}

    def retrieve(question, collection):
        seen.update(question=question, collection=collection)
        return "FILE: storage.py\n\ndef load_todos(): ..."

    async with db_session_maker() as db:
        run_id = await _seed(db, result={"success": True, "answer": "It reads todos.json."})
        stored = await OE.grade_run(db, run_id, "sample", judge=judge, retrieve=retrieve)
    kind, case, answer, context = judge.calls[0]
    assert (kind, answer) == ("answer", "It reads todos.json.") and "load_todos" in context
    assert case["prompt"] == "what does it do?" and seen == {"question": "what does it do?", "collection": "repo_r1"}
    assert (stored.trigger, stored.passed, stored.score, stored.evaluator_name) == ("sample", True, 0.9, "judge:stub-judge")
    assert "correctness=5" in stored.rationale


@integration
async def test_an_edit_is_graded_on_the_change_it_made(db_session_maker):
    judge = StubJudge(passed=False)
    async with db_session_maker() as db:
        run_id = await _seed(db, mode="editing", result={"success": True, "edited_files": {"main.py": "new"},
                                                          "original_files": {"main.py": "old"}})
        stored = await OE.grade_run(db, run_id, "thumbs_down", judge=judge, retrieve=lambda q, c: "")
    kind, case, after, before = judge.calls[0]
    assert (kind, after, before) == ("code", {"main.py": "new"}, {"main.py": "old"}) and case["mode"] == "editing"
    assert stored.passed is False and stored.trigger == "thumbs_down"


@integration
async def test_a_new_project_is_graded_on_its_files(db_session_maker):
    judge = StubJudge()
    async with db_session_maker() as db:
        run_id = await _seed(db, mode="generation", result={"success": True, "files": {"app.py": "print(1)"}})
        await OE.grade_run(db, run_id, "sample", judge=judge)
    assert judge.calls[0][0] == "code" and judge.calls[0][2] == {"app.py": "print(1)"} and judge.calls[0][3] is None


@integration
async def test_failed_runs_are_not_graded(db_session_maker):
    judge = StubJudge()
    async with db_session_maker() as db:
        run_id = await _seed(db, success=False)
        assert await OE.grade_run(db, run_id, "sample", judge=judge) is None
        assert judge.calls == [] and (await db.execute(select(func.count()).select_from(EvalResult))).scalar_one() == 0


@integration
async def test_a_run_is_graded_once_even_if_sampled_and_then_rated_down(db_session_maker):
    judge = StubJudge()
    async with db_session_maker() as db:
        run_id = await _seed(db, result={"answer": "x"})
        first = await OE.grade_run(db, run_id, "sample", judge=judge, retrieve=lambda q, c: "")
        again = await OE.grade_run(db, run_id, "thumbs_down", judge=judge, retrieve=lambda q, c: "")
        assert first.id == again.id and len(judge.calls) == 1
        assert (await db.execute(select(func.count()).select_from(EvalResult))).scalar_one() == 1


@integration
async def test_a_judge_failure_never_raises_and_stores_nothing(db_session_maker):
    async with db_session_maker() as db:
        run_id = await _seed(db, result={"answer": "x"})
        assert await OE.grade_run(db, run_id, "sample", judge=StubJudge(explode=True), retrieve=lambda q, c: "") is None
        assert (await db.execute(select(func.count()).select_from(EvalResult))).scalar_one() == 0


@integration
async def test_deleting_the_chat_deletes_its_verdicts(db_session_maker):
    async with db_session_maker() as db:
        run_id = await _seed(db, result={"answer": "x"})
        await OE.grade_run(db, run_id, "sample", judge=StubJudge(), retrieve=lambda q, c: "")
    async with db_session_maker() as db:
        await db.delete(await db.get(Session, "s1"))
        await db.commit()
        assert (await db.execute(select(func.count()).select_from(EvalResult))).scalar_one() == 0


# ------------------------------------------------------------------ the hooks

@integration
@pytest.mark.parametrize("sampled, expected", [(True, ["sample"]), (False, [])])
async def test_a_finished_run_is_graded_only_when_sampled(db_session_maker, monkeypatch, sampled, expected):
    monkeypatch.setattr(M, "async_session", db_session_maker)
    graded = []

    async def fake_grade(db, run_id, trigger, **kw):
        graded.append(trigger)

    monkeypatch.setattr(M, "grade_run", fake_grade)
    monkeypatch.setattr(M, "is_sampled", lambda run_id: sampled)

    async def fake_qa(**kwargs):
        return {"success": True, "answer": "42", "metrics": METRICS, "result": {}, "task_id": "t"}

    monkeypatch.setattr(M.task_manager, "execute_question_answering", fake_qa)
    async with db_session_maker() as db:
        db.add(User(id="u1", email="u1@example.com", name="u1", provider="google"))
        db.add(Session(id="s-live", user_id="u1", mode=SessionMode.QUESTION_ANSWERING, messages=[], is_active=True))
        await db.commit()
    await M._run_generation_task(mode=SessionMode.QUESTION_ANSWERING, session_id="s-live", prompt="q", project_root="./x",
                                 project_id=None, repository_id=None, repo_path=".", collection_name="c", recursion_limit=5)
    assert graded == expected


@pytest.fixture
async def client(db_session_maker):
    async def get_db():
        async with db_session_maker() as db:
            yield db

    M.app.dependency_overrides[M.get_db] = get_db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=M.app), base_url="http://test") as c:
            yield c
    finally:
        M.app.dependency_overrides.clear()


def _as(user_id):
    M.app.dependency_overrides[M.get_current_user] = lambda: {"sub": user_id}


@integration
@pytest.mark.parametrize("rating, enabled, expected", [("down", True, ["thumbs_down"]), ("up", True, []), ("down", False, [])])
async def test_thumbs_down_schedules_grading(client, db_session_maker, monkeypatch, rating, enabled, expected):
    scheduled = []

    async def fake_bg(session_factory, run_id, trigger):
        scheduled.append(trigger)

    monkeypatch.setattr(M, "grade_run_in_new_session", fake_bg)
    monkeypatch.setattr(M, "ON_THUMBS_DOWN", enabled)
    async with db_session_maker() as db:
        await _seed(db, result={"answer": "x"})
    _as("u1")
    r = await client.post("/feedback", json={"session_id": "s1", "rating": rating})
    assert r.status_code == 200 and scheduled == expected


@integration
async def test_the_admin_view_is_for_admins_only(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, result={"answer": "x"})
    _as("u1")
    assert (await client.get("/admin/evals")).status_code == 403


@integration
async def test_the_admin_view_lists_verdicts_with_the_users_rating_and_a_summary(client, db_session_maker):
    from backend import feedback_store

    async with db_session_maker() as db:
        await _seed(db, user_id="boss", session_id="s-boss", role=UserRole.ADMIN, result={"answer": "x"})
        run_id = await _seed(db, user_id="u1", session_id="s-user", result={"answer": "y"})
        await OE.grade_run(db, run_id, "thumbs_down", judge=StubJudge(passed=False), retrieve=lambda q, c: "")
        await feedback_store.save_feedback(db, session_id="s-user", user_id="u1", rating="down")
    _as("boss")
    body = (await client.get("/admin/evals")).json()
    (item,) = body["items"]
    assert (item["run_id"], item["trigger"], item["passed"], item["user_rating"], item["mode"]) == (run_id, "thumbs_down", False, "down", "question_answering")
    assert body["summary"] == [{"mode": "question_answering", "graded": 1, "judged": 1, "avg_score": 0.2, "pass_rate": 0.0}]
