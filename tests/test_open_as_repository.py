"""'Open as Repository': a generated project becomes a repository for the editing pipeline (needs Postgres)."""
import os

import httpx
import pytest
from sqlalchemy import select

import backend.main as M
from backend.db_models import Project, ProjectStatus, Repository, User

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(db_session_maker, monkeypatch, tmp_path):
    async def get_db():
        async with db_session_maker() as db:
            yield db

    monkeypatch.chdir(tmp_path)                  # the endpoint writes under ./temp_repos
    M.app.dependency_overrides[M.get_db] = get_db
    M.app.dependency_overrides[M.get_current_user] = lambda: {"sub": "u1"}     # no email: not an admin
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=M.app), base_url="http://test") as c:
            yield c
    finally:
        M.app.dependency_overrides.clear()


FILES = {"index.html": "<html></html>\n", "js/app.js": "run()\n", "gone.txt": None}


async def _seed(db, *, owner="u1", status=ProjectStatus.COMPLETED, files=FILES):
    db.add(User(id="u1", email="u1@example.com", name="u1", provider="google"))
    db.add(User(id="u2", email="u2@example.com", name="u2", provider="google"))
    await db.flush()
    db.add(Project(id="p1", user_id=owner, name="Calculator App", prompt="make it", files=files, status=status))
    await db.commit()


async def _repo(db_session_maker, repo_id):
    async with db_session_maker() as db:
        return (await db.execute(select(Repository).where(Repository.id == repo_id))).scalar_one_or_none()


async def test_opening_a_project_makes_an_unindexed_repo_with_its_files_and_keeps_the_project(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)

    r = await client.post("/projects/p1/repository")
    assert r.status_code == 200 and r.json()["created"] is True
    repo = await _repo(db_session_maker, r.json()["repository_id"])

    assert repo.user_id == "u1" and repo.name == "Calculator App" and repo.provider == "generated"
    assert repo.is_indexed is False                                       # the repo page starts indexing
    assert repo.files == {"index.html": "<html></html>\n", "js/app.js": "run()\n"}    # snapshot for rehydration
    with open(os.path.join(repo.local_path, "js", "app.js"), encoding="utf-8") as f:
        assert f.read() == "run()\n"

    project = (await client.get("/projects/p1")).json()                   # still listed, now linked
    assert project["status"] == "completed" and project["repository_id"] == repo.id
    assert project["files"]["index.html"] == "<html></html>\n"


async def test_opening_twice_returns_the_same_repo(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)
    first = (await client.post("/projects/p1/repository")).json()
    second = (await client.post("/projects/p1/repository")).json()
    assert second == {"repository_id": first["repository_id"], "created": False}
    async with db_session_maker() as db:
        assert len((await db.execute(select(Repository))).scalars().all()) == 1


async def test_a_deleted_repo_unlinks_the_project_and_opening_again_makes_a_new_one(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)
    first = (await client.post("/projects/p1/repository")).json()["repository_id"]
    assert (await client.delete(f"/repositories/{first}")).status_code == 200

    assert (await client.get("/projects/p1")).json()["repository_id"] is None   # button offers it again
    again = (await client.post("/projects/p1/repository")).json()
    assert again["created"] is True and again["repository_id"] != first


async def test_a_generated_repo_does_not_use_up_the_github_or_local_repo_slot(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db)
    assert (await client.post("/projects/p1/repository")).status_code == 200
    gh = await client.post("/repositories", json={"name": "gh", "url": "https://github.com/a/b", "provider": "github"})
    assert gh.status_code == 200, gh.text
    local = await client.post("/repositories", json={"name": "loc", "local_path": "x", "provider": "local"})
    assert local.status_code == 200, local.text


async def test_only_a_completed_project_with_files_can_be_opened(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, status=ProjectStatus.IN_PROGRESS)
    assert (await client.post("/projects/p1/repository")).status_code == 400


async def test_someone_elses_project_404s(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed(db, owner="u2")
    assert (await client.post("/projects/p1/repository")).status_code == 404


async def test_project_paths_cannot_escape_the_repo_folder(client, db_session_maker, tmp_path):
    async with db_session_maker() as db:
        await _seed(db, files={"ok.py": "1", "../../evil.py": "x", "/abs.py": "y"})
    repo = await _repo(db_session_maker, (await client.post("/projects/p1/repository")).json()["repository_id"])
    assert set(repo.files) == {"ok.py", "abs.py"}
    assert not (tmp_path / "evil.py").exists() and not (tmp_path.parent / "evil.py").exists()
