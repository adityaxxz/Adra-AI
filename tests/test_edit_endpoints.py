"""API-level tests for what the repository page relies on after an editing run (need Postgres)."""
import httpx
import pytest
from sqlalchemy import select

import backend.main as M
from backend.db_models import Repository, Session, SessionMode, User

pytestmark = pytest.mark.integration


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


async def _seed(db, tmp_path, snapshot, *, session_result=None, session_owner="u1"):
    db.add(User(id="u1", email="u1@example.com", name="u1", provider="google"))
    db.add(User(id="u2", email="u2@example.com", name="u2", provider="google"))
    await db.flush()
    db.add(Repository(id="r1", user_id="u1", name="r", provider="github", collection_name="repo_r1",
                      local_path=str(tmp_path), files=snapshot))
    if session_result is not None:
        db.add(Session(id="s1", user_id=session_owner, mode=SessionMode.EDITING, repository_id="r1",
                       messages=[], is_active=False, result=session_result))
    await db.commit()


async def test_files_panel_lists_files_the_agent_created_whatever_their_extension(client, db_session_maker, tmp_path):
    # Production bug: the listing only knew 9 extensions, so a created todo.txt never appeared in the panel.
    (tmp_path / "index.html").write_text("<html>", encoding="utf-8")
    (tmp_path / "todo.txt").write_text("buy milk", encoding="utf-8")
    (tmp_path / "style.cc").write_text("// a", encoding="utf-8")
    (tmp_path / "data.csv").write_text("a,b", encoding="utf-8")          # in the repo, never touched by the agent
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"index.html": "<html>", "todo.txt": "buy milk", "style.cc": "// a"})

    files = (await client.get("/repositories/r1")).json()["files"]
    assert {k.replace("\\", "/") for k in files} == {"index.html", "todo.txt", "style.cc"}
    assert files["todo.txt"] == "buy milk"


async def test_files_panel_shows_what_is_on_disk_now_and_drops_files_that_are_gone(client, db_session_maker, tmp_path):
    (tmp_path / "index.html").write_text("<html>NEW</html>", encoding="utf-8")
    async with db_session_maker() as db:      # snapshot is stale and also lists a file that no longer exists
        await _seed(db, tmp_path, {"index.html": "<html>OLD</html>", "gone.txt": "x"})

    files = (await client.get("/repositories/r1")).json()["files"]
    assert files == {"index.html": "<html>NEW</html>"}


def _run_result():
    return {
        "success": True,
        "edited_files": {"a.py": "new a", "new.txt": "created"},
        "original_files": {"a.py": "old a", "new.txt": None},
    }


async def test_resolve_reject_restores_disk_snapshot_and_persists_the_decision(client, db_session_maker, tmp_path):
    (tmp_path / "a.py").write_text("new a", encoding="utf-8")
    (tmp_path / "new.txt").write_text("created", encoding="utf-8")
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"a.py": "new a", "new.txt": "created"}, session_result=_run_result())

    r = await client.post("/repositories/r1/edits/s1/resolve", json={"reject": ["a.py", "new.txt"]})
    assert r.status_code == 200 and r.json()["review"] == {"a.py": "rejected", "new.txt": "rejected"}
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "old a" and not (tmp_path / "new.txt").exists()

    async with db_session_maker() as db:
        repo = (await db.execute(select(Repository))).scalar_one()
        session = (await db.execute(select(Session))).scalar_one()
    assert repo.files == {"a.py": "old a"}                                  # snapshot follows the disk
    assert session.result["edit_review"] == {"a.py": "rejected", "new.txt": "rejected"}   # survives a reload

    again = await client.post("/repositories/r1/edits/s1/resolve", json={"accept": ["a.py"]})
    assert again.json()["review"]["a.py"] == "rejected"                     # a decided file can't be flipped


async def test_resolve_accept_with_a_hand_edit_writes_it_everywhere(client, db_session_maker, tmp_path):
    (tmp_path / "a.py").write_text("new a", encoding="utf-8")
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"a.py": "new a"}, session_result=_run_result())

    r = await client.post("/repositories/r1/edits/s1/resolve", json={"accept": ["a.py"], "edited": {"a.py": "my a"}})
    assert r.json()["review"] == {"a.py": "accepted"}
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "my a"
    async with db_session_maker() as db:
        assert (await db.execute(select(Repository))).scalar_one().files == {"a.py": "my a"}


async def test_resolve_leaves_a_file_alone_if_it_changed_since_the_run(client, db_session_maker, tmp_path):
    (tmp_path / "a.py").write_text("a later run's work", encoding="utf-8")
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"a.py": "a later run's work"}, session_result=_run_result())

    r = await client.post("/repositories/r1/edits/s1/resolve", json={"reject": ["a.py"]})
    assert r.json()["conflicts"] == ["a.py"]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "a later run's work"


async def test_resolve_404s_for_someone_elses_session(client, db_session_maker, tmp_path):
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {}, session_result=_run_result(), session_owner="u2")
    r = await client.post("/repositories/r1/edits/s1/resolve", json={"reject": ["a.py"]})
    assert r.status_code == 404
