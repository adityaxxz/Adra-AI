"""User ratings of finished runs (POST /feedback): who can rate what, replacing a rating, and cascades."""
import asyncio

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import backend.main as M
from backend import feedback_store, run_store
from backend.db_models import AgentRun, Feedback, Session, SessionMode, User

METRICS = {"llm_calls": 1, "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0001, "latency_ms": 10.0, "retries": 0,
           "per_agent": {"explainer": {"calls": 1, "input_tokens": 10, "output_tokens": 5, "latency_ms": 10.0}}}

integration = pytest.mark.integration


async def _seed(db, *, session_id="s1", user_id="u1", with_run=True, prompt="what is this?"):
    if not (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none():
        db.add(User(id=user_id, email=f"{user_id}@example.com", name=user_id, provider="google"))
    db.add(Session(id=session_id, user_id=user_id, mode=SessionMode.QUESTION_ANSWERING, messages=[], is_active=False))
    await db.commit()
    if with_run:
        run = await run_store.record_agent_run(
            db, session_id=session_id, mode="question_answering", prompt=prompt,
            task_result={"success": True, "metrics": METRICS}, provider="groq", model="m",
        )
        return run.id


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ------------------------------------------------------------------ request validation (no DB)

def test_only_up_or_down_is_a_valid_rating():
    assert M.FeedbackRequest(session_id="s", rating="up").rating == "up"
    with pytest.raises(ValidationError):
        M.FeedbackRequest(session_id="s", rating="meh")
    with pytest.raises(ValidationError):
        M.FeedbackRequest(session_id="s", rating="UP")


def test_comments_are_length_limited():
    M.FeedbackRequest(session_id="s", rating="down", comment="x" * 2000)
    with pytest.raises(ValidationError):
        M.FeedbackRequest(session_id="s", rating="down", comment="x" * 2001)


async def test_the_store_rejects_an_unknown_rating_before_touching_the_database():
    with pytest.raises(ValueError):
        await feedback_store.save_feedback(None, session_id="s", user_id="u", rating="sideways")


# --------------------------------------------------------------------------- the store

@integration
async def test_a_user_can_rate_the_run_of_their_own_session(db_session_maker):
    async with db_session_maker() as db:
        run_id = await _seed(db)
        fb = await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating="down", comment="  wrong file  ")
    assert (fb.run_id, fb.user_id, fb.rating, fb.comment) == (run_id, "u1", "down", "wrong file")
    async with db_session_maker() as db:
        row = (await db.execute(select(Feedback))).scalar_one()
    assert row.rating == "down" and row.created_at is not None


@integration
async def test_rating_again_replaces_the_rating_instead_of_adding_one(db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)
        await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating="up", comment="nice")
        await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating="down", comment=None)
        rows = (await db.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1 and rows[0].rating == "down" and rows[0].comment is None


@integration
async def test_a_blank_comment_is_stored_as_no_comment(db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)
        fb = await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating="up", comment="   ")
    assert fb.comment is None


@integration
async def test_nobody_can_rate_someone_elses_session(db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, session_id="s-alice", user_id="alice")
        db.add(User(id="bob", email="bob@example.com", name="bob", provider="google"))
        await db.commit()
        assert await feedback_store.save_feedback(db, session_id="s-alice", user_id="bob", rating="down") is None
        assert await _count(db, Feedback) == 0


@integration
async def test_there_is_nothing_to_rate_for_an_unknown_session_or_one_with_no_recorded_run(db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, session_id="no-run", with_run=False)
        assert await feedback_store.save_feedback(db, session_id="ghost", user_id="u1", rating="up") is None
        assert await feedback_store.save_feedback(db, session_id="no-run", user_id="u1", rating="up") is None
        assert await _count(db, Feedback) == 0


@integration
async def test_two_users_each_keep_their_own_rating_of_the_same_run(db_session_maker):
    """Sessions are per user, so this guards the unique key rather than a reachable flow: it is (run, user)."""
    async with db_session_maker() as db:
        run_id = await _seed(db)
        db.add(User(id="u2", email="u2@example.com", name="u2", provider="google"))
        await db.commit()
        db.add_all([Feedback(id="f1", run_id=run_id, user_id="u1", rating="up"),
                    Feedback(id="f2", run_id=run_id, user_id="u2", rating="down")])
        await db.commit()
        assert await _count(db, Feedback) == 2


@integration
async def test_the_database_itself_refuses_a_second_rating_for_the_same_run_and_user(db_session_maker):
    """The guarantee behind the upsert: the race test below may not always hit the race, this one always checks the key."""
    async with db_session_maker() as db:
        run_id = await _seed(db)
        db.add(Feedback(id="f1", run_id=run_id, user_id="u1", rating="up"))
        await db.commit()
        db.add(Feedback(id="f2", run_id=run_id, user_id="u1", rating="down"))
        with pytest.raises(IntegrityError):
            await db.commit()


@integration
async def test_a_double_click_cannot_create_two_ratings_or_an_error(db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)

    async def rate(rating):
        async with db_session_maker() as db:
            return await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating=rating)

    results = await asyncio.gather(*[rate("up"), rate("down"), rate("up"), rate("down")])
    assert all(r is not None for r in results)
    async with db_session_maker() as db:
        assert await _count(db, Feedback) == 1


@integration
async def test_deleting_the_session_deletes_its_feedback_and_deleting_the_user_does_too(db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, session_id="s1")
        await _seed(db, session_id="s2", user_id="u2", prompt="other")
        await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating="down", comment="private note")
        await feedback_store.save_feedback(db, session_id="s2", user_id="u2", rating="up")
    async with db_session_maker() as db:
        await db.delete((await db.execute(select(Session).where(Session.id == "s1"))).scalar_one())
        await db.commit()
        assert [f.user_id for f in (await db.execute(select(Feedback))).scalars()] == ["u2"]
        await db.delete((await db.execute(select(User).where(User.id == "u2"))).scalar_one())
        await db.commit()
        assert await _count(db, Feedback) == 0


@integration
async def test_the_latest_run_is_the_one_rated_when_a_session_has_several(db_session_maker):
    async with db_session_maker() as db:
        first = await _seed(db)
        second = (await run_store.record_agent_run(
            db, session_id="s1", mode="question_answering", prompt="again",
            task_result={"success": True, "metrics": METRICS}, provider="groq", model="m")).id
        fb = await feedback_store.save_feedback(db, session_id="s1", user_id="u1", rating="up")
    assert first != second and fb.run_id == second


# -------------------------------------------------------------------------- the endpoint

@pytest.fixture
async def client(db_session_maker):
    async def get_db():
        async with db_session_maker() as db:
            yield db

    M.app.dependency_overrides[M.get_db] = get_db
    M.app.dependency_overrides[M.get_current_user] = lambda: {"sub": "u1"}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=M.app), base_url="http://test") as c:
            yield c
    finally:
        M.app.dependency_overrides.clear()


@integration
async def test_post_feedback_saves_a_rating_and_reports_the_run(client, db_session_maker):
    async with db_session_maker() as db:
        run_id = await _seed(db)
    r = await client.post("/feedback", json={"session_id": "s1", "rating": "up", "comment": "great"})
    assert r.status_code == 200 and r.json() == {"run_id": run_id, "rating": "up"}
    async with db_session_maker() as db:
        assert (await db.execute(select(Feedback.comment))).scalar_one() == "great"


@integration
async def test_post_feedback_returns_404_when_there_is_no_finished_run(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, session_id="no-run", with_run=False)
    assert (await client.post("/feedback", json={"session_id": "no-run", "rating": "up"})).status_code == 404
    assert (await client.post("/feedback", json={"session_id": "ghost", "rating": "up"})).status_code == 404


@integration
async def test_post_feedback_rejects_a_bad_rating_with_422(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)
    assert (await client.post("/feedback", json={"session_id": "s1", "rating": "five stars"})).status_code == 422
    assert (await client.post("/feedback", json={"rating": "up"})).status_code == 422


@integration
async def test_post_feedback_requires_a_logged_in_user(db_session_maker):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=M.app), base_url="http://test") as c:
        r = await c.post("/feedback", json={"session_id": "s1", "rating": "up"})
    assert r.status_code in (401, 403)
