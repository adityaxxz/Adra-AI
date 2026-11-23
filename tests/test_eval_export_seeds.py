import pytest
import yaml
from sqlalchemy import select

from backend import run_store
from backend.db_models import Feedback, Session, SessionMode, User
from evals import export_seeds as X


def rows(*items):
    return [{"mode": m, "user_prompt": p, "status": "success"} for m, p in items]


# -------------------------------------------------------------------- pure logic

def test_candidates_are_unique_and_skip_prompts_the_dataset_already_has():
    r = rows(("generation", "Build a  todo app"), ("generation", "build a todo app"), ("generation", "A brand new idea"),
             ("generation", "Create a simple to-do list web application using HTML, CSS, and JavaScript"))
    out = X.build_candidates(r, {"Create a simple to-do list web application using HTML, CSS, and JavaScript"})
    assert [c["prompt"] for c in out] == ["Build a  todo app", "A brand new idea"]


def test_candidates_are_marked_for_review_and_never_claim_a_fixture():
    out = X.build_candidates(rows(("generation", "g"), ("editing", "e"), ("question_answering", "q")), set())
    by = {c["mode"]: c for c in out}
    assert all(c["needs_review"] and c["source"] == "seeded-export" for c in out)
    assert "fixture" not in by["generation"]
    assert by["editing"]["fixture"] is None and by["question_answering"]["fixture"] is None, "they refer to the user's own repo"
    assert len({c["id"] for c in out}) == 3


def test_mode_filter_and_empty_prompts():
    out = X.build_candidates(rows(("generation", "g1"), ("editing", "e1"), ("generation", "   ")), set(), mode="generation")
    assert [c["prompt"] for c in out] == ["g1"]


def test_candidates_are_not_part_of_the_loaded_suite():
    from evals import dataset as D
    assert "seed_candidates" not in "".join(D.SUITE_FILES.values())


def test_the_exporter_refuses_to_run_without_an_explicit_user():
    with pytest.raises(SystemExit):
        X.main([])


# ------------------------------------------------------------ privacy (real Postgres)

@pytest.mark.integration
async def test_only_the_requested_users_prompts_are_read_and_eval_sessions_are_excluded(db_session_maker):
    async with db_session_maker() as db:
        for uid in ("alice", "bob"):
            db.add(User(id=uid, email=f"{uid}@example.com", name=uid, provider="google"))
        for sid, uid in (("s-a1", "alice"), ("s-a2", "alice"), ("eval-xyz-case-1", "alice"), ("s-b1", "bob")):
            db.add(Session(id=sid, user_id=uid, mode=SessionMode.GENERATION, messages=[], is_active=False))
        await db.commit()
        for sid, prompt in (("s-a1", "alice's first idea"), ("s-a2", "alice's second idea"),
                            ("eval-xyz-case-1", "a harness prompt"), ("s-b1", "BOB'S PRIVATE PROMPT")):
            await run_store.record_agent_run(db, session_id=sid, mode="generation", prompt=prompt,
                                             task_result={"success": True, "metrics": {}}, provider="p", model="m")

    dsn = db_session_maker.kw["bind"].url.render_as_string(hide_password=False)
    got = await X.fetch_rows(dsn, "ALICE@example.com")                  # case-insensitive match
    prompts = sorted(r["user_prompt"] for r in got)
    assert prompts == ["alice's first idea", "alice's second idea"]
    assert "BOB'S PRIVATE PROMPT" not in str(got) and "a harness prompt" not in str(got)
    assert await X.fetch_rows(dsn, "nobody@example.com") == []


# ------------------------------------------------------------------ user ratings travel with the prompt

def rated(mode, prompt, rating, comment=None):
    return {"mode": mode, "user_prompt": prompt, "status": "success", "rating": rating, "comment": comment}


def test_a_rated_prompt_carries_its_rating_and_comment_and_an_unrated_one_carries_nothing():
    out = X.build_candidates([rated("editing", "fix the login", "down", "broke the build"), *rows(("editing", "add a footer"))], set())
    by = {c["prompt"]: c for c in out}
    assert by["fix the login"]["feedback"] == {"rating": "down", "comment": "broke the build"}
    assert "feedback" not in by["add a footer"]


def test_a_later_rated_repeat_of_a_prompt_is_not_lost_to_the_unrated_first_one():
    out = X.build_candidates([*rows(("generation", "Build a todo app")), rated("generation", "build a  todo app", "down")], set())
    assert len(out) == 1 and out[0]["feedback"]["rating"] == "down"


def test_the_first_rating_of_a_repeated_prompt_wins():
    out = X.build_candidates([rated("generation", "idea", "up"), rated("generation", "idea", "down")], set())
    assert len(out) == 1 and out[0]["feedback"]["rating"] == "up"


@pytest.mark.integration
async def test_the_export_reads_the_requesting_users_own_rating_and_nobody_elses(db_session_maker):
    async with db_session_maker() as db:
        for uid in ("alice", "bob"):
            db.add(User(id=uid, email=f"{uid}@example.com", name=uid, provider="google"))
        for sid, uid in (("s-a", "alice"), ("s-a2", "alice"), ("s-b", "bob")):
            db.add(Session(id=sid, user_id=uid, mode=SessionMode.GENERATION, messages=[], is_active=False))
        await db.commit()
        ids = {}
        for sid, prompt in (("s-a", "rated idea"), ("s-a2", "unrated idea"), ("s-b", "bob's idea")):
            ids[sid] = (await run_store.record_agent_run(db, session_id=sid, mode="generation", prompt=prompt,
                                                         task_result={"success": True, "metrics": {}}, provider="p", model="m")).id
        db.add_all([Feedback(id="f1", run_id=ids["s-a"], user_id="alice", rating="down", comment="too slow"),
                    Feedback(id="f2", run_id=ids["s-b"], user_id="bob", rating="up", comment="bob's secret note"),
                    # not reachable through the API (sessions are per user), but the export must never show another user's note
                    Feedback(id="f3", run_id=ids["s-a2"], user_id="bob", rating="up", comment="bob's note on alice's run")])
        await db.commit()

    dsn = db_session_maker.kw["bind"].url.render_as_string(hide_password=False)
    got = {r["user_prompt"]: r for r in await X.fetch_rows(dsn, "alice@example.com")}
    assert got["rated idea"]["rating"] == "down" and got["rated idea"]["comment"] == "too slow"
    assert got["unrated idea"]["rating"] is None, "bob's rating of alice's run must not be attributed to alice"
    assert "bob's secret note" not in str(got) and "bob's idea" not in str(got) and "bob's note on alice's run" not in str(got)
