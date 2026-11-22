"""Tests that need a real Postgres. Skipped automatically when none is reachable
(set TEST_DATABASE_URL, or run `docker compose up -d postgres`)."""
import pytest
from sqlalchemy import select, text

import backend.main as M
from backend.db_models import (
    Base, Project, ProjectStatus, Repository, Session, SessionMode, User,
)

pytestmark = pytest.mark.integration


async def _seed_user(db, uid="u1"):
    db.add(User(id=uid, email=f"{uid}@example.com", name=uid, provider="google"))


# ------------------------------------------------------------------ orphaned runs

async def test_orphan_sweep_fails_interrupted_runs_and_leaves_everything_else_alone(db_session_maker, monkeypatch):
    monkeypatch.setattr(M, "async_session", db_session_maker)
    async with db_session_maker() as db:
        await _seed_user(db)
        db.add(Project(id="p_orphan", user_id="u1", name="o", prompt="x", files={}, status=ProjectStatus.IN_PROGRESS))
        db.add(Project(id="p_done", user_id="u1", name="d", prompt="x", files={"a.py": "1"}, status=ProjectStatus.COMPLETED))
        db.add(Project(id="p_pending", user_id="u1", name="p", prompt="x", files={}, status=ProjectStatus.PENDING))
        db.add(Session(id="s_orphan", user_id="u1", mode=SessionMode.GENERATION, messages=[], is_active=True))
        db.add(Session(id="s_done", user_id="u1", mode=SessionMode.QUESTION_ANSWERING, messages=[], is_active=False,
                       result={"success": True, "answer": "hi"}))
        await db.commit()

    await M.fail_orphaned_runs()

    async with db_session_maker() as db:
        projects = {p.id: p for p in (await db.execute(select(Project))).scalars()}
        sessions = {s.id: s for s in (await db.execute(select(Session))).scalars()}

    assert projects["p_orphan"].status == ProjectStatus.FAILED
    assert projects["p_orphan"].error_message == M.ORPHANED_RUN_ERROR
    assert sessions["s_orphan"].is_active is False and sessions["s_orphan"].completed_at is not None
    assert sessions["s_orphan"].result == {"success": False, "error": M.ORPHANED_RUN_ERROR}

    assert projects["p_done"].status == ProjectStatus.COMPLETED and projects["p_done"].files == {"a.py": "1"}
    assert projects["p_pending"].status == ProjectStatus.PENDING
    assert sessions["s_done"].result == {"success": True, "answer": "hi"}


async def test_orphan_sweep_is_idempotent(db_session_maker, monkeypatch):
    monkeypatch.setattr(M, "async_session", db_session_maker)
    async with db_session_maker() as db:
        await _seed_user(db)
        db.add(Session(id="s1", user_id="u1", mode=SessionMode.EDITING, messages=[], is_active=True))
        await db.commit()
    await M.fail_orphaned_runs()
    await M.fail_orphaned_runs()          # runs on every boot
    async with db_session_maker() as db:
        assert (await db.execute(select(Session).where(Session.is_active.is_(True)))).scalars().all() == []


# ---------------------------------------------------------------- startup DDL

async def test_lifespan_ddl_is_idempotent_and_upgrades_an_old_schema(db_session_maker, monkeypatch):
    """There is no Alembic: new columns on existing tables ship as `ALTER TABLE ... IF NOT EXISTS`
    in the lifespan hook. It runs on every boot, so it must be repeatable, and it must upgrade a
    database created before `repositories.files` existed."""
    engine = db_session_maker.kw["bind"]
    monkeypatch.setattr(M, "engine", engine)
    monkeypatch.setattr(M, "async_session", db_session_maker)

    async with engine.begin() as conn:           # simulate the pre-snapshot schema
        await conn.execute(text("ALTER TABLE repositories DROP COLUMN files"))
    async with db_session_maker() as db:         # and a run the previous process died in the middle of
        await _seed_user(db)
        db.add(Session(id="killed-by-deploy", user_id="u1", mode=SessionMode.QUESTION_ANSWERING, messages=[], is_active=True))
        await db.commit()

    for _ in range(2):                            # two boots in a row
        async with M.lifespan(M.app):
            pass

    async with engine.connect() as conn:
        cols = {r[0] for r in await conn.execute(text(
            "select column_name from information_schema.columns where table_name = 'repositories'"))}
    assert "files" in cols
    async with db_session_maker() as db:         # booting is what clears orphans, not just the helper
        killed = (await db.execute(select(Session).where(Session.id == "killed-by-deploy"))).scalar_one()
        assert killed.is_active is False


async def test_new_tables_are_created_on_boot_without_a_migration(db_session_maker, monkeypatch):
    """Whole new tables (agent_runs, run_steps, ...) need no ALTER: create_all adds them."""
    engine = db_session_maker.kw["bind"]
    monkeypatch.setattr(M, "engine", engine)
    monkeypatch.setattr(M, "async_session", db_session_maker)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE run_steps"))
        await conn.execute(text("DROP TABLE agent_runs"))

    async with M.lifespan(M.app):
        pass

    async with engine.connect() as conn:
        tables = {r[0] for r in await conn.execute(text(
            "select table_name from information_schema.tables where table_schema = 'public'"))}
    assert {"agent_runs", "run_steps"} <= tables


async def test_repository_files_snapshot_round_trips_through_the_json_column(db_session_maker):
    snapshot = {"main.py": "print(1)", "src/app.py": "def f():\n    return 'ünïcode'\n"}
    async with db_session_maker() as db:
        await _seed_user(db)
        db.add(Repository(id="r1", user_id="u1", name="r", provider="local", collection_name="repo_r1", files=snapshot))
        await db.commit()
    async with db_session_maker() as db:
        repo = (await db.execute(select(Repository).where(Repository.id == "r1"))).scalar_one()
        assert repo.files == snapshot


# ------------------------------------------------------------------------ health

async def test_health_is_degraded_when_only_the_vector_store_is_down(db_session_maker, monkeypatch):
    """Postgres reachable, Qdrant not (conftest points QDRANT_URL at nothing)."""
    import httpx

    monkeypatch.setattr(M, "engine", db_session_maker.kw["bind"])
    # In-process on *this* loop: the sync TestClient runs the app on another loop,
    # which asyncpg connections created here can't be used from.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=M.app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["vector_store"].startswith("error")
    assert body["status"] == "degraded"
