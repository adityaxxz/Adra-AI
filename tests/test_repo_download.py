"""Downloading a repository as a ZIP: the zip builder, and the endpoint (needs Postgres)."""
import io
import os
import zipfile

import httpx
import pytest

import backend.main as M
import backend.repo_zip as RZ
from backend.db_models import Repository, User
from backend.repo_zip import RepoZipEmpty, RepoZipTooLarge, build_repo_zip, zip_filename


def _write(root, rel, text="x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _names(zip_file):
    with zipfile.ZipFile(zip_file) as zf:
        return set(zf.namelist())


def test_zip_has_every_file_whatever_its_extension_with_forward_slash_paths(tmp_path):
    _write(tmp_path, "index.html", "<html>")
    _write(tmp_path, "todo.txt", "buy milk")
    _write(tmp_path, "src/deep/app.py", "print(1)")
    f, size = build_repo_zip(str(tmp_path))
    try:
        assert size == len(f.read()) and f.seek(0) == 0
        assert _names(f) == {"index.html", "todo.txt", "src/deep/app.py"}
        with zipfile.ZipFile(f) as zf:
            assert zf.read("todo.txt") == b"buy milk"
    finally:
        f.close()


def test_zip_leaves_out_junk_dirs_and_secrets_but_keeps_real_source_dirs(tmp_path):
    for rel in ["a.py", "lib/util.py", "build/gen.py", "dist/x.js", ".env.example",
                ".git/config", "node_modules/p/i.js", "__pycache__/a.pyc", ".venv/bin/x",
                ".env", ".env.local", ".env.production"]:
        _write(tmp_path, rel)
    f, _ = build_repo_zip(str(tmp_path))
    try:
        # lib/, build/, dist/ are skipped by the indexer but are user source: a download keeps them.
        assert _names(f) == {"a.py", "lib/util.py", "build/gen.py", "dist/x.js", ".env.example"}
    finally:
        f.close()


def test_zip_skips_symlinks_so_nothing_outside_the_project_leaks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside, "secret.txt", "top secret")
    proj = tmp_path / "proj"
    _write(proj, "a.py")
    try:
        os.symlink(outside / "secret.txt", proj / "link.txt")
        os.symlink(outside, proj / "linkdir", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted here")
    f, _ = build_repo_zip(str(proj))
    try:
        assert _names(f) == {"a.py"}
    finally:
        f.close()


def test_zip_of_nothing_downloadable_is_an_error(tmp_path):
    with pytest.raises(RepoZipEmpty):
        build_repo_zip(str(tmp_path))
    _write(tmp_path, "node_modules/x.js")
    _write(tmp_path, ".env")
    with pytest.raises(RepoZipEmpty):
        build_repo_zip(str(tmp_path))


def test_zip_refuses_a_project_over_the_size_cap(tmp_path):
    _write(tmp_path, "a.txt", "a" * 600)
    _write(tmp_path, "b.txt", "b" * 600)
    with pytest.raises(RepoZipTooLarge):
        build_repo_zip(str(tmp_path), max_bytes=1000)
    f, _ = build_repo_zip(str(tmp_path), max_bytes=1200)
    f.close()


def test_zip_filename_is_header_safe():
    assert zip_filename("test 2") == "test-2.zip"
    name = zip_filename('a"b\r\nX-Evil: 1/c\\d')
    assert name == "a-b-X-Evil-1-c-d.zip" and not any(c in name for c in '"\r\n/\\ ')
    assert zip_filename("") == "repository.zip" and zip_filename("///") == "repository.zip"


integration = pytest.mark.integration


# --- endpoint --------------------------------------------------------------------------------

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


async def _seed(db, path, snapshot=None, owner="u1", name="my repo"):
    db.add(User(id="u1", email="u1@example.com", name="u1", provider="google"))
    db.add(User(id="u2", email="u2@example.com", name="u2", provider="google"))
    await db.flush()
    db.add(Repository(id="r1", user_id=owner, name=name, provider="github", collection_name="repo_r1",
                      local_path=str(path), files=snapshot or {}))
    await db.commit()


@integration
async def test_download_streams_the_current_files_as_a_zip(client, db_session_maker, tmp_path):
    _write(tmp_path, "index.html", "<html>EDITED</html>")       # newer than the snapshot
    _write(tmp_path, "todo.txt", "buy milk")                     # not an indexable type
    _write(tmp_path, ".env", "KEY=secret")
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"index.html": "<html>OLD</html>"})

    r = await client.get("/repositories/r1/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == 'attachment; filename="my-repo.zip"'
    assert int(r.headers["content-length"]) == len(r.content)
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert set(zf.namelist()) == {"index.html", "todo.txt"}
        assert zf.read("index.html") == b"<html>EDITED</html>"


@integration
async def test_download_rebuilds_a_wiped_working_copy_from_the_snapshot(client, db_session_maker, tmp_path):
    gone = tmp_path / "wiped"                                    # e.g. an ephemeral dyno filesystem reset
    async with db_session_maker() as db:
        await _seed(db, gone, {"a.py": "print(1)", "pkg/b.py": "print(2)"})

    r = await client.get("/repositories/r1/download")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert set(zf.namelist()) == {"a.py", "pkg/b.py"}


@integration
async def test_download_404s_for_someone_elses_repository(client, db_session_maker, tmp_path):
    _write(tmp_path, "a.py")
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"a.py": "x"}, owner="u2")
    assert (await client.get("/repositories/r1/download")).status_code == 404
    assert (await client.get("/repositories/nope/download")).status_code == 404


@integration
async def test_download_404s_when_there_is_nothing_to_zip(client, db_session_maker, tmp_path):
    async with db_session_maker() as db:
        await _seed(db, tmp_path)                                # empty folder, empty snapshot
    assert (await client.get("/repositories/r1/download")).status_code == 404


@integration
async def test_download_413s_when_the_project_is_too_big(client, db_session_maker, tmp_path, monkeypatch):
    _write(tmp_path, "a.py", "a" * 50)
    async with db_session_maker() as db:
        await _seed(db, tmp_path, {"a.py": "a" * 50})
    real = RZ.build_repo_zip
    monkeypatch.setattr(RZ, "build_repo_zip", lambda root: real(root, max_bytes=10))
    r = await client.get("/repositories/r1/download")
    assert r.status_code == 413


# --- generated projects: GET /projects/{id}/download -------------------------------------------

async def _seed_project(db, files, owner="u1", name="calculator"):
    from backend.db_models import Project
    db.add(User(id="u1", email="u1@example.com", name="u1", provider="google"))
    db.add(User(id="u2", email="u2@example.com", name="u2", provider="google"))
    await db.flush()
    db.add(Project(id="p1", user_id=owner, name=name, prompt="make it", files=files))
    await db.commit()


@integration
async def test_project_download_is_a_zip_of_the_generated_files(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed_project(db, {"index.html": "<html>", "js/app.js": "x()", "gone.txt": None})
    r = await client.get("/projects/p1/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == 'attachment; filename="calculator-project.zip"'
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert set(zf.namelist()) == {"index.html", "js/app.js"} and zf.read("js/app.js") == b"x()"


@integration
async def test_project_download_survives_a_project_name_that_is_not_a_valid_header(client, db_session_maker):
    # Production bug: the raw name went into Content-Disposition, so a non-latin-1 name was a 500.
    async with db_session_maker() as db:
        await _seed_project(db, {"a.py": "1"}, name='计算器 "calc" v2')
    r = await client.get("/projects/p1/download")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="calc-v2-project.zip"'


@integration
async def test_project_download_404s_for_someone_elses_project_and_400s_when_empty(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed_project(db, {"a.py": "1"}, owner="u2")
    assert (await client.get("/projects/p1/download")).status_code == 404


@integration
async def test_project_download_400s_when_there_are_no_files(client, db_session_maker):
    async with db_session_maker() as db:
        await _seed_project(db, {})
    assert (await client.get("/projects/p1/download")).status_code == 400
