"""Shared test setup.

Runs before any `agent` / `backend` import (pytest loads conftest first), and
forces the environment so that tests can never reach a real LLM, tracing
backend, vector store or database - even on a dev machine whose `.env` has live
credentials. The modules call `load_dotenv()` themselves, but that never
overrides a variable that is already set, so setting them here wins.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --- LLM / embeddings: construct the clients with throwaway keys; calls are always stubbed ---
os.environ["LLM_PROVIDER"] = "groq"
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["NVIDIA_API_KEY"] = "test-key"

# --- tracing off (empty/false values are "set", so load_dotenv() leaves them alone) ---
for _var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ[_var] = "false"
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""

# --- datastores: point at nothing. Integration tests bring their own database. ---
os.environ["QDRANT_URL"] = "http://127.0.0.1:6399"
os.environ.pop("QDRANT_API_KEY", None)
os.environ["DATABASE_URL"] = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing"

import pytest  # noqa: E402

# Local docker-compose Postgres (see docker-compose.yml), used when TEST_DATABASE_URL isn't set.
_LOCAL_ADMIN = "postgresql://adrai:adrai_password@localhost:5433/adrai"
_LOCAL_TEST_DB = "adrai_pytest"


@pytest.fixture
def tmp_repo(tmp_path):
    """An empty directory standing in for a checked-out repository."""
    return tmp_path


def write_files(root: Path, files: dict) -> None:
    for rel, content in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


@pytest.fixture
def make_repo(tmp_path):
    def _make(files: dict) -> Path:
        write_files(tmp_path, files)
        return tmp_path
    return _make


async def _resolve_database_url() -> str:
    """URL of a database the tests may freely create/drop tables in, or skip."""
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit.replace("postgres://", "postgresql+asyncpg://", 1).replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
    import asyncpg

    try:
        conn = await asyncio.wait_for(asyncpg.connect(_LOCAL_ADMIN), timeout=3)
    except Exception as e:  # no local docker Postgres either
        pytest.skip(f"no Postgres available for integration tests (set TEST_DATABASE_URL): {e!r}")
    try:
        exists = await conn.fetchval("select 1 from pg_database where datname = $1", _LOCAL_TEST_DB)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{_LOCAL_TEST_DB}"')
    finally:
        await conn.close()
    return f"postgresql+asyncpg://adrai:adrai_password@localhost:5433/{_LOCAL_TEST_DB}"


@pytest.fixture
async def db_session_maker():
    """Fresh schema on a real Postgres for each test; yields an async sessionmaker.

    Tables are dropped first, so point TEST_DATABASE_URL only at a database you
    don't mind being wiped (never at real data).
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db_models import Base

    url = await _resolve_database_url()
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def new_id() -> str:
    return str(uuid.uuid4())
