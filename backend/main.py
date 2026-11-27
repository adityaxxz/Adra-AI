from dotenv import load_dotenv
load_dotenv()

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import select, func, text, update
from sqlalchemy.exc import SQLAlchemyError
from prometheus_fastapi_instrumentator import Instrumentator
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, ValidationError, Field
import os
import uuid
from datetime import datetime, timedelta
from slowapi.errors import RateLimitExceeded
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import zipfile
import io
import shutil
import logging
import tempfile

# Load Admin Emails from environment variable (case-insensitive check)
ADMIN_EMAILS_RAW = os.getenv("ADMIN_EMAILS", "")
ADMIN_EMAILS = {email.strip().lower() for email in ADMIN_EMAILS_RAW.split(",") if email.strip()}

from backend.auth import (
    oauth_callback, GoogleOAuth, GitHubOAuth, get_current_user,
    Token, OAuthConfig
)
from backend.db_models import Base, User, UserRole, Project, Repository, Session, SessionMode, ProjectStatus, AgentRun, EvalResult, Feedback
from backend.websocket_manager import manager, ProgressReporter
from backend.background_tasks import task_manager, _indexing_message
from backend.run_store import record_agent_run
from backend.feedback_store import save_feedback
from backend.online_eval import ON_THUMBS_DOWN, grade_run, grade_run_in_new_session, is_sampled
from backend.guardrails import check_prompt, enforce_rate_limit
from backend.edit_review import apply_review
from agent.llm_client import LLM_PROVIDER, MODEL_NAME
from agent.repository.service import index_repository
from backend.rate_limit import limiter, RATE_LIMITS, rate_limit_handler
from backend.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    generic_exception_handler,
    not_found_exception_handler
)

# Import agent tools for project root management
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://adrai:adrai_password@localhost:5433/adrai")
# Normalize scheme: Heroku/Neon inject postgres:// or postgresql://, but
# SQLAlchemy's asyncpg engine requires the postgresql+asyncpg:// scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# asyncpg does NOT accept sslmode/channel_binding as URL query params
# (those are libpq/psycopg2 conventions). Strip them and pass ssl via connect_args.
_connect_args: dict = {}
if "sslmode=require" in DATABASE_URL or "sslmode=prefer" in DATABASE_URL:
    import urllib.parse as _urlparse
    _parsed = _urlparse.urlparse(DATABASE_URL)
    _qs = _urlparse.parse_qs(_parsed.query)
    # Remove libpq-specific params that asyncpg rejects
    for _param in ("sslmode", "channel_binding"):
        _qs.pop(_param, None)
    _new_query = _urlparse.urlencode({k: v[0] for k, v in _qs.items()})
    DATABASE_URL = _parsed._replace(query=_new_query).geturl()
    _connect_args["ssl"] = True

# echo=False: echo=True attached a second plain-text handler (every statement logged twice), buried
# real events, and logged bound parameters - which included generated source and Q&A answers.
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True, connect_args=_connect_args)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


ORPHANED_RUN_ERROR = "Run was interrupted by a server restart. Please try again."


async def fail_orphaned_runs() -> None:
    """Mark runs that were killed mid-flight as failed.

    Agent runs execute as in-process background tasks (see
    `_run_generation_task`), so a dyno restart or deploy kills them with no
    chance to record a result: the session stays `is_active` and the project
    stays IN_PROGRESS, leaving the UI spinning forever with no error. Nothing
    can legitimately be running during startup, so anything still marked active
    here was orphaned by the previous process.

    Assumes a single web process (see the Dockerfile's `--workers 1`); with
    multiple dynos/workers this would also cancel runs live on another process.
    """
    async with async_session() as db:
        try:
            sessions = await db.execute(
                update(Session)
                .where(Session.is_active.is_(True))
                .values(
                    is_active=False,
                    completed_at=datetime.utcnow(),
                    result={"success": False, "error": ORPHANED_RUN_ERROR},
                )
            )
            # Leaves status FAILED, which is what the UI offers "Regenerate" on.
            projects = await db.execute(
                update(Project)
                .where(Project.status == ProjectStatus.IN_PROGRESS)
                .values(status=ProjectStatus.FAILED, error_message=ORPHANED_RUN_ERROR)
            )
            await db.commit()

            if sessions.rowcount or projects.rowcount:
                logger.warning(
                    f"Marked orphaned runs as failed after restart: "
                    f"{sessions.rowcount} session(s), {projects.rowcount} project(s)"
                )
        except Exception as e:
            # Never block startup on this - a failed sweep only means stale rows.
            await db.rollback()
            logger.error(f"Failed to sweep orphaned runs: {e}", exc_info=True)


# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS projects_created_count INTEGER DEFAULT 0 NOT NULL;"))
        await conn.execute(text("ALTER TABLE repositories ADD COLUMN IF NOT EXISTS files JSON;"))
        await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;"))
        await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS repository_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS prompt_versions JSON;"))
    await fail_orphaned_runs()
    yield
    # Shutdown
    await engine.dispose()


# FastAPI app
app = FastAPI(title="Adra-AI API", version="1.0.0", lifespan=lifespan)

# Configure rate limiting
# TEMPORARILY DISABLED FOR TESTING
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Configure error handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
app.add_exception_handler(StarletteHTTPException, not_found_exception_handler)

# Configure structured (JSON) logging with per-run correlation IDs
from agent.logging_config import configure_logging
configure_logging(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS middleware
# Read allowed origins from env so production locks to the Vercel domain.
# ALLOWED_ORIGINS takes precedence (comma-separated list); falls back to FRONTEND_URL.
_frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
_raw_allowed_origins = os.getenv("ALLOWED_ORIGINS")
if _raw_allowed_origins:
    _allowed_origins = [origin.strip() for origin in _raw_allowed_origins.split(",") if origin.strip()]
else:
    _allowed_origins = [_frontend_url]
    if not os.getenv("FRONTEND_URL"):
        # No production config supplied at all - assume local development.
        _allowed_origins.append("http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency: Database session
async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


# Pydantic models for API
class UserCreate(BaseModel):
    email: str
    name: str
    avatar_url: Optional[str] = None
    provider: str


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class RepositoryCreate(BaseModel):
    name: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    provider: str = "github"


class FeedbackRequest(BaseModel):
    session_id: str
    rating: Literal["up", "down"]
    comment: Optional[str] = Field(default=None, max_length=2000)


class EditReviewRequest(BaseModel):
    accept: List[str] = Field(default_factory=list)
    reject: List[str] = Field(default_factory=list)
    # Hand-edited content for accepted files, {path: text}; written over the agent's version.
    edited: Dict[str, str] = Field(default_factory=dict)


class GenerationRequest(BaseModel):
    prompt: str
    mode: SessionMode = SessionMode.GENERATION
    project_id: Optional[str] = None
    repository_id: Optional[str] = None
    recursion_limit: int = 100
    session_id: Optional[str] = None  # Allow frontend to provide session ID


# =========================
# Health Check
# =========================

@app.get("/health")
# @limiter.limit("60/minute")  # TEMPORARILY DISABLED FOR TESTING
async def health_check(request: Request):
    """Health check endpoint. Actually probes Postgres and Qdrant instead of
    returning a static payload, so it can be trusted as a readiness signal."""
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        logger.error(f"Health check: database probe failed: {e}", exc_info=True)
        checks["database"] = f"error: {e}"

    try:
        from agent.repository.vector_store import client as qdrant_client
        await asyncio.to_thread(qdrant_client.get_collections)
        checks["vector_store"] = "ok"
    except Exception as e:
        logger.error(f"Health check: vector store probe failed: {e}", exc_info=True)
        checks["vector_store"] = f"error: {e}"

    healthy = all(v == "ok" for v in checks.values())
    body = {
        "status": "healthy" if healthy else "degraded",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }
    return body if healthy else JSONResponse(status_code=503, content=body)


# =========================
# OAuth Endpoints
# =========================

@app.get("/auth/{provider}/login")
# @limiter.limit(RATE_LIMITS["auth"])  # TEMPORARILY DISABLED FOR TESTING
async def oauth_login(request: Request, provider: str, redirect_uri: Optional[str] = None):
    """Get OAuth authorization URL."""
    if redirect_uri is None:
        redirect_uri = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/auth/{provider}/callback"
    
    if provider == "google":
        return {"authorization_url": GoogleOAuth.get_authorization_url(redirect_uri)}
    elif provider == "github":
        return {"authorization_url": GitHubOAuth.get_authorization_url(redirect_uri)}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider}"
        )


@app.get("/auth/{provider}/callback")
async def oauth_callback_endpoint(
    provider: str,
    code: str,
    redirect_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Handle OAuth callback."""
    if redirect_uri is None:
        redirect_uri = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/auth/{provider}/callback"
    
    # Exchange code for token and get user info
    token_data = await oauth_callback(provider, code, redirect_uri)
    
    # Check if user exists, create if not
    result = await db.execute(select(User).where(User.id == token_data.user["id"]))
    user = result.scalar_one_or_none()
    
    if not user:
        # Check if user exists by email
        email_result = await db.execute(select(User).where(User.email == token_data.user["email"]))
        user = email_result.scalar_one_or_none()
        
        if not user:
            user = User(
                id=token_data.user["id"],
                email=token_data.user["email"],
                name=token_data.user["name"],
                avatar_url=token_data.user.get("avatar_url"),
                provider=token_data.user["provider"]
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            # User exists with the same email but a different OAuth ID (different provider).
            # We sign them in as the existing user and issue a new Token with the existing user's ID.
            from backend.auth import create_access_token
            jwt_token = create_access_token(
                data={
                    "sub": user.id,
                    "email": user.email,
                    "name": user.name,
                    "provider": user.provider
                }
            )
            token_data = Token(
                access_token=jwt_token,
                token_type=token_data.token_type,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "avatar_url": user.avatar_url or token_data.user.get("avatar_url"),
                    "provider": user.provider
                }
            )
    
    return token_data


@app.get("/auth/me")
async def get_current_user_endpoint(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return current_user


# =========================
# Projects Endpoints
# =========================

@app.post("/projects", response_model=dict)
# @limiter.limit(RATE_LIMITS["api"])  # TEMPORARILY DISABLED FOR TESTING
async def create_project(
    request: Request,
    project: ProjectCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new project."""
    # Enforce limit of 1 project for non-admin users to prevent API key exhaustion
    user_email = current_user.get("email", "").lower()
    db_user = None
    if user_email not in ADMIN_EMAILS:
        result = await db.execute(select(User).where(User.id == current_user["sub"]))
        db_user = result.scalar_one_or_none()
        if db_user and db_user.projects_created_count >= 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Limit exceeded: Non-admin users are only allowed to create 1 project."
            )
            
    project_id = str(uuid.uuid4())
    
    db_project = Project(
        id=project_id,
        user_id=current_user["sub"],
        name=project.name,
        description=project.description,
        prompt=project.prompt,
        files={},
        status=ProjectStatus.PENDING
    )
    
    db.add(db_project)
    
    # Increment projects_created_count on the user object
    if user_email not in ADMIN_EMAILS and db_user:
        db_user.projects_created_count += 1
        db.add(db_user)
        
    await db.commit()
    await db.refresh(db_project)
    
    return {
        "id": db_project.id,
        "name": db_project.name,
        "description": db_project.description,
        "prompt": db_project.prompt,
        "status": db_project.status,
        "created_at": db_project.created_at.isoformat()
    }


@app.get("/projects", response_model=List[dict])
async def list_projects(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all projects for the current user."""
    result = await db.execute(
        select(Project).where(Project.user_id == current_user["sub"]).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat() if p.updated_at else None
        }
        for p in projects
    ]


@app.get("/projects/{project_id}", response_model=dict)
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific project."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user["sub"]
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "prompt": project.prompt,
        "files": project.files,
        "status": project.status,
        "error_message": project.error_message,
        "integration_fixes": project.integration_fixes,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "started_at": project.started_at.isoformat() if project.started_at else None,
        "completed_at": project.completed_at.isoformat() if project.completed_at else None,
        "repository_id": await _live_project_repo_id(db, project, current_user["sub"]),
    }


async def _live_project_repo_id(db: AsyncSession, project: Project, user_id: str) -> Optional[str]:
    """The repo made from this project, or None if there isn't one or it has since been deleted."""
    if not project.repository_id:
        return None
    result = await db.execute(
        select(Repository.id).where(Repository.id == project.repository_id, Repository.user_id == user_id)
    )
    return result.scalar_one_or_none()


def _write_project_files(root: str, files: dict) -> dict:
    """Write a generated project's files under `root`; returns the {path: content} actually written."""
    real_root = os.path.realpath(root)
    written = {}
    for rel, content in (files or {}).items():
        if content is None:
            continue
        rel = rel.replace("\\", "/").lstrip("/")
        full = os.path.realpath(os.path.join(real_root, rel))
        if os.path.commonpath([real_root, full]) != real_root:
            continue                                   # never write outside the repo folder
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        written[rel] = content
    return written


@app.post("/projects/{project_id}/repository")
async def open_project_as_repository(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Copy a generated project into a new repository so it can be indexed, asked about and edited.

    The project itself is left as it is. Calling this again returns the same repository instead of
    making another one (`created: false`); if that repository was deleted, a new one is made.
    Generated repositories don't count toward the local/GitHub repository limits: there is at
    most one per project.
    """
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user["sub"])
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    existing = await _live_project_repo_id(db, project, current_user["sub"])
    if existing:
        return {"repository_id": existing, "created": False}

    if project.status != ProjectStatus.COMPLETED or not any(v is not None for v in (project.files or {}).values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a completed project with files can be opened as a repository",
        )

    repo_id = str(uuid.uuid4())
    local_path = os.path.join("temp_repos", f"generated_{repo_id}")
    written = await asyncio.to_thread(_write_project_files, local_path, project.files)

    repository = Repository(
        id=repo_id,
        user_id=current_user["sub"],
        name=project.name,
        local_path=local_path,
        provider="generated",
        collection_name=f"repo_{repo_id.replace('-', '_')}",
        is_indexed=False,
        files=written,                 # snapshot, so the repo survives an ephemeral disk wipe
    )
    db.add(repository)
    project.repository_id = repo_id
    await db.commit()
    return {"repository_id": repo_id, "created": True}


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a project."""
    logger.info(f"Delete request for project: {project_id}")

    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user["sub"]
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        logger.warning(f"Project not found: {project_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    logger.info(f"Deleting project: {project.name}")

    try:
        # First, delete all sessions that reference this project
        # This resolves the foreign key constraint issue
        sessions_result = await db.execute(
            select(Session).where(Session.project_id == project_id)
        )
        sessions = sessions_result.scalars().all()
        logger.info(f"Found {len(sessions)} sessions to delete")

        for session in sessions:
            await db.delete(session)
            logger.info(f"Deleted session: {session.id}")

        await db.commit()

        # Now delete the project
        await db.delete(project)
        await db.commit()

        logger.info(f"Project deleted successfully: {project_id}")
        return {"message": "Project deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting project: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project: {str(e)}"
        )


@app.get("/projects/{project_id}/download")
async def download_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Download project files as a ZIP file."""
    from backend.repo_zip import zip_filename

    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user["sub"]
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if not project.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no files to download"
        )
    
    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path, file_content in project.files.items():
            if file_content is not None:
                # Add file to ZIP with the proper path structure
                zip_file.writestr(file_path, file_content)
    
    zip_buffer.seek(0)
    
    # Return the ZIP file as a StreamingResponse
    return StreamingResponse(
        io.BytesIO(zip_buffer.getvalue()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename(project.name + "-project")}"'
        }
    )


# =========================
# Repositories Endpoints
# =========================

@app.post("/repositories", response_model=dict)
# @limiter.limit(RATE_LIMITS["api"])  # TEMPORARILY DISABLED FOR TESTING
async def create_repository(
    request: Request,
    repository: RepositoryCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new repository."""
    # Enforce repo limits for non-admin users (1 local repo and 1 github/url repo)
    user_email = current_user.get("email", "").lower()
    if user_email not in ADMIN_EMAILS:
        if repository.provider == "local":
            stmt = select(func.count(Repository.id)).where(
                Repository.user_id == current_user["sub"],
                Repository.provider == "local"
            )
            result = await db.execute(stmt)
            local_count = result.scalar()
            if local_count >= 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Limit exceeded: Non-admin users are only allowed 1 local repository."
                )
        else:
            stmt = select(func.count(Repository.id)).where(
                Repository.user_id == current_user["sub"],
                Repository.provider.notin_(["local", "generated"])
            )
            result = await db.execute(stmt)
            github_count = result.scalar()
            if github_count >= 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Limit exceeded: Non-admin users are only allowed 1 GitHub repository."
                )

    repo_id = str(uuid.uuid4())
    collection_name = f"repo_{repo_id.replace('-', '_')}"
    
    db_repo = Repository(
        id=repo_id,
        user_id=current_user["sub"],
        name=repository.name,
        url=repository.url,
        local_path=repository.local_path,
        provider=repository.provider,
        collection_name=collection_name,
        is_indexed=False
    )
    
    db.add(db_repo)
    await db.commit()
    await db.refresh(db_repo)
    
    return {
        "id": db_repo.id,
        "name": db_repo.name,
        "url": db_repo.url,
        "provider": db_repo.provider,
        "collection_name": db_repo.collection_name,
        "is_indexed": db_repo.is_indexed,
        "created_at": db_repo.created_at.isoformat()
    }


@app.get("/repositories", response_model=List[dict])
async def list_repositories(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all repositories for the current user."""
    result = await db.execute(
        select(Repository).where(Repository.user_id == current_user["sub"]).order_by(Repository.created_at.desc())
    )
    repositories = result.scalars().all()
    
    return [
        {
            "id": r.id,
            "name": r.name,
            "url": r.url,
            "provider": r.provider,
            "collection_name": r.collection_name,
            "is_indexed": r.is_indexed,
            # files_count may be 0/stale for repos indexed before the column was
            # correctly populated; fall back to the files JSON snapshot count so
            # the UI always shows the real number.
            "files_count": r.files_count or len(r.files or {}),
            "chunks_count": r.chunks_count,
            "created_at": r.created_at.isoformat(),
            "last_indexed_at": r.last_indexed_at.isoformat() if r.last_indexed_at else None
        }
        for r in repositories
    ]


@app.get("/repositories/{repository_id}", response_model=dict)
async def get_repository(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific repository."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.user_id == current_user["sub"]
        )
    )
    repository = result.scalar_one_or_none()
    
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found"
        )
    
    # Get files structure if repository is local
    # Filter to only show supported files (same as scanner)
    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".html": "html",
        ".css": "css",
        ".md": "markdown",
        ".json": "json",
    }
    
    IGNORE_DIRS = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".next",
        "lib",
    }
    
    from agent.repository.service import ensure_repo_on_disk
    rehydrated_path = ensure_repo_on_disk(repository.local_path, repository.files, repository.id)
    if rehydrated_path != repository.local_path:
        repository.local_path = rehydrated_path
        await db.commit()

    files = {}
    if repository.local_path and os.path.exists(repository.local_path):
        try:
            for root, dirs, filenames in os.walk(repository.local_path):
                # Filter out ignored directories
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                
                for filename in filenames:
                    # Skip hidden files
                    if filename.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, repository.local_path)
                    
                    # Check if file extension is supported
                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext not in SUPPORTED_EXTENSIONS:
                        continue
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            files[relative_path] = f.read()
                    except Exception as e:
                        # Skip files that can't be read as text
                        files[relative_path] = None
        except Exception as e:
            logger.error(f"Error reading repository files: {e}")

        # The walk above only lists indexable extensions, so a file the agent created or
        # edited with another one (todo.txt, a .cc file) never showed up, though it's on
        # disk. Those files are recorded in `repository.files`; list them too, from disk.
        listed = {p.replace("\\", "/") for p in files}
        for rel in repository.files or {}:
            full = os.path.join(repository.local_path, rel)
            if rel in listed or ".." in rel.split("/") or not os.path.isfile(full):
                continue
            try:
                with open(full, "r", encoding="utf-8") as f:
                    files[rel] = f.read()
            except Exception:
                files[rel] = None

    return {
        "id": repository.id,
        "name": repository.name,
        "url": repository.url,
        "local_path": repository.local_path,
        "provider": repository.provider,
        "collection_name": repository.collection_name,
        "is_indexed": repository.is_indexed,
        "files_count": repository.files_count or len(repository.files or {}),
        "chunks_count": repository.chunks_count,
        "created_at": repository.created_at.isoformat(),
        "updated_at": repository.updated_at.isoformat() if repository.updated_at else None,
        "last_indexed_at": repository.last_indexed_at.isoformat() if repository.last_indexed_at else None,
        "files": files
    }


@app.get("/repositories/{repository_id}/download")
async def download_repository(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Download the repository's current files (including edits not yet reviewed) as a ZIP.

    Built on demand into a temp file and streamed, so nothing is stored anywhere.
    """
    from agent.repository.service import ensure_repo_on_disk
    from backend.repo_zip import build_repo_zip, zip_filename, RepoZipEmpty, RepoZipTooLarge

    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.user_id == current_user["sub"]
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    rehydrated_path = await asyncio.to_thread(
        ensure_repo_on_disk, repository.local_path, repository.files, repository.id
    )
    if rehydrated_path != repository.local_path:
        repository.local_path = rehydrated_path
        await db.commit()
    if not repository.local_path or not os.path.isdir(repository.local_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository has no files to download")

    try:
        zip_file, size = await asyncio.to_thread(build_repo_zip, repository.local_path)
    except RepoZipEmpty:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository has no files to download")
    except RepoZipTooLarge:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Repository is too large to download as a ZIP",
        )

    def stream():
        try:
            while chunk := zip_file.read(64 * 1024):
                yield chunk
        finally:
            zip_file.close()

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename(repository.name)}"',
            "Content-Length": str(size),
        },
    )


async def _run_indexing_task(repository_id: str, session_id: str):
    """Resolve the repo on disk (rehydrate or clone) and index it into Qdrant.

    Runs as a background task for the same reason as `_run_generation_task`:
    cloning a repo and embedding every chunk routinely runs past Heroku's 30s
    HTTP router timeout (H12). Progress, completion and errors all reach the
    frontend over the WebSocket, which isn't subject to that timeout.

    The blocking git clone and whole-repo file reads are pushed onto threads -
    this coroutine shares the event loop with every other request (and with
    the WebSocket that reports its own progress), so it must not block it.
    """
    from agent.repository.service import (
        ensure_repo_on_disk,
        snapshot_repo_files,
        clone_github_repo,
        clone_dir_for,
    )
    from agent.repository.vector_store import count_chunks

    reporter = ProgressReporter(session_id)

    async with async_session() as db:
        try:
            result = await db.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repository = result.scalar_one_or_none()
            if not repository:
                await reporter.error("Repository not found")
                return

            rehydrated_path = await asyncio.to_thread(
                ensure_repo_on_disk, repository.local_path, repository.files, repository.id
            )
            if rehydrated_path != repository.local_path:
                repository.local_path = rehydrated_path
                await db.commit()

            # Determine repo path - prioritize local path for local repos
            if repository.local_path:
                repo_path = repository.local_path
            elif repository.url:
                # Clone GitHub repositories to local path if needed
                if repository.url.startswith('http'):
                    local_repo_path = clone_dir_for(repository.name, repository.url)
                    # Ensure temp_repos directory exists
                    os.makedirs("./temp_repos", exist_ok=True)
                    repo_path = await asyncio.to_thread(
                        clone_github_repo, repository.url, local_repo_path
                    )
                    logger.info(f"Cloned repository to: {repo_path}")
                    # Update the repository's local_path in the database
                    repository.local_path = repo_path
                    await db.commit()
                else:
                    repo_path = repository.url
            else:
                await reporter.error("Repository URL or local path must be provided")
                return

            task_result = await task_manager.index_repository_task(
                session_id=session_id,
                repo_path=repo_path,
                collection_name=repository.collection_name
            )

            if not task_result["success"]:
                # index_repository_task already reported the error over the socket.
                return

            repository.is_indexed = True
            repository.last_indexed_at = datetime.utcnow()
            repository.files = await asyncio.to_thread(snapshot_repo_files, repo_path)
            # The task's stats are per-run under incremental indexing (a no-change
            # re-index reports 0), so take the totals from the snapshot and the
            # collection instead.
            repository.files_count = len(repository.files)
            total_chunks = await asyncio.to_thread(count_chunks, repository.collection_name)
            if total_chunks is not None:
                repository.chunks_count = total_chunks
            await db.commit()
            # Sent after the commit, so the page can read is_indexed straight away.
            await reporter.update(
                "complete", f"{repository.files_count} files, {repository.chunks_count or 0} chunks",
                progress=100,
            )

        except Exception as e:
            logger.error(f"Background indexing task failed: {e}", exc_info=True)
            await db.rollback()
            await reporter.error(_indexing_message(e))


@app.post("/repositories/{repository_id}/index")
async def index_repository_endpoint(
    repository_id: str,
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Schedule repository indexing and return immediately.

    Ownership is verified synchronously; the clone + embed itself runs in the
    background (see `_run_indexing_task`) and reports over the WebSocket.
    """
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.user_id == current_user["sub"]
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found"
        )

    background_tasks.add_task(
        _run_indexing_task,
        repository_id=repository_id,
        session_id=session_id
    )

    return {
        "session_id": session_id,
        "repository_id": repository_id,
        "status": "processing"
    }


@app.delete("/repositories/{repository_id}")
async def delete_repository(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a repository."""
    logger.info(f"Delete request for repository: {repository_id} by user: {current_user['sub']}")

    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.user_id == current_user["sub"]
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found"
        )

    logger.info(f"Deleting repository: {repository.name} (local_path={repository.local_path}, collection={repository.collection_name})")

    try:
        # First, delete all sessions that reference this repository
        # This resolves the foreign key constraint issue
        sessions_result = await db.execute(
            select(Session).where(Session.repository_id == repository_id)
        )
        sessions = sessions_result.scalars().all()
        logger.info(f"Found {len(sessions)} sessions to delete")

        for session in sessions:
            await db.delete(session)
            logger.info(f"Deleted session: {session.id}")

        await db.commit()

        # Delete Qdrant collection if exists
        from agent.repository.vector_store import clear_collection
        try:
            clear_collection(repository.collection_name)
            logger.info(f"Cleared collection: {repository.collection_name}")
        except Exception as e:
            logger.warning(f"Failed to clear collection: {e}", exc_info=True)

        # Delete uploaded files if they exist
        if repository.local_path and repository.provider == 'local':
            try:
                import shutil
                if os.path.exists(repository.local_path):
                    shutil.rmtree(repository.local_path)
                    logger.info(f"Deleted local files: {repository.local_path}")
            except Exception as e:
                logger.warning(f"Failed to delete local files: {e}", exc_info=True)

        # Delete repository from database
        await db.delete(repository)
        await db.commit()

        logger.info("Repository deleted successfully")

        return {"message": "Repository deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting repository: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete repository: {str(e)}"
        )


@app.post("/upload-folder")
async def upload_folder(
    files: List[UploadFile] = File(...),
    repository_name: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a local folder and create a repository."""
    # Enforce limit of 1 local repo for non-admin users
    user_email = current_user.get("email", "").lower()
    if user_email not in ADMIN_EMAILS:
        stmt = select(func.count(Repository.id)).where(
            Repository.user_id == current_user["sub"],
            Repository.provider == "local"
        )
        result = await db.execute(stmt)
        local_count = result.scalar()
        if local_count >= 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Limit exceeded: Non-admin users are only allowed 1 local repository upload."
            )

    # Create a permanent directory to store uploaded files
    upload_dir = os.path.join("uploaded_repos", f"{current_user['sub']}_{repository_name}_{int(datetime.utcnow().timestamp())}")
    os.makedirs(upload_dir, exist_ok=True)
    
    try:
        # Process uploaded files
        for file in files:
            # file.filename is the webkitRelativePath: "folder-name/subdir/file.css"
            # Strip the leading folder component so files land directly in upload_dir
            path_parts = file.filename.replace('\\', '/').split('/')
            relative_path = '/'.join(path_parts[1:]) if len(path_parts) > 1 else file.filename
            
            # Construct the file path without the top-level folder prefix
            file_path = os.path.join(upload_dir, relative_path)
            
            # Create directories if needed
            file_dir = os.path.dirname(file_path)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)
            
            # Write the file content
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)
        
        # Create repository record
        repo_id = str(uuid.uuid4())
        collection_name = f"repo_{repo_id.replace('-', '_')}"

        # Snapshot file contents into the DB immediately so the repo can be
        # rehydrated from `repository.files` even if the dyno restarts before
        # the user triggers indexing (Heroku wipes the ephemeral filesystem on
        # every restart, so we can't rely solely on the on-disk copy).
        from agent.repository.service import snapshot_repo_files
        files_snapshot = await asyncio.to_thread(snapshot_repo_files, upload_dir)

        repository = Repository(
            id=repo_id,
            user_id=current_user["sub"],
            name=repository_name,
            local_path=upload_dir,
            provider="local",
            collection_name=collection_name,
            is_indexed=False,
            files=files_snapshot,
        )
        
        db.add(repository)
        await db.commit()
        await db.refresh(repository)
        
        return {
            "success": True,
            "repository_id": repository.id,
            "local_path": upload_dir,
            "files_count": len(files),
            "message": "Folder uploaded successfully"
        }
        
    except Exception as e:
        # Clean up on error
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload folder: {str(e)}"
        )


# =========================
# Generation Endpoints
# =========================

async def refresh_repository_index(repo_path: Optional[str], collection_name: Optional[str]) -> None:
    """Bring a repository's search index in line with its files on disk, after an edit run wrote them or a review
    restored or hand-edited them. Without this, Q&A and the edit planner kept retrieving the code as it was before the
    edit (seen live: Ask mode still reported the old button colour after the change was accepted). Incremental: only
    changed files are re-embedded. Never raises - a failed refresh must not break the run or the review."""
    if not repo_path or not collection_name:
        return
    try:
        await asyncio.to_thread(index_repository, repo_path, collection_name)
    except Exception as e:
        logger.warning(f"Search index refresh failed for {collection_name!r}: {e}")


async def _run_generation_task(
    mode: SessionMode,
    session_id: str,
    prompt: str,
    project_root: str,
    project_id: Optional[str],
    repository_id: Optional[str],
    repo_path: Optional[str],
    collection_name: Optional[str],
    recursion_limit: int
):
    """Run the agent pipeline and persist its result. Executed as a FastAPI
    background task (after the /generate response is already sent) because
    these pipelines regularly run past Heroku's 30s HTTP router timeout
    (H12) - the caller must not await this inline. Uses its own DB session
    since the request-scoped one is gone by the time this runs. The actual
    answer/result reaches the frontend via the WebSocket `complete` event
    (see websocket_manager.ProgressReporter), which isn't subject to the
    HTTP router timeout."""
    async with async_session() as db:
        try:
            if mode == SessionMode.GENERATION:
                task_result = await task_manager.execute_project_generation(
                    session_id=session_id,
                    user_prompt=prompt,
                    project_root=project_root,
                    recursion_limit=recursion_limit
                )

                if project_id:
                    result = await db.execute(
                        select(Project).where(Project.id == project_id)
                    )
                    project = result.scalar_one_or_none()
                    if project:
                        if task_result["success"]:
                            project.files = task_result["files"]
                            project.status = ProjectStatus.COMPLETED
                            project.integration_fixes = task_result.get("integration_fixes", 0)
                            project.completed_at = datetime.utcnow()
                        else:
                            project.status = ProjectStatus.FAILED
                            project.error_message = task_result.get("error", "Unknown error occurred during generation")
                        await db.commit()

            elif mode == SessionMode.EDITING:
                task_result = await task_manager.execute_repository_editing(
                    session_id=session_id,
                    user_prompt=prompt,
                    repo_path=repo_path,
                    collection_name=collection_name,
                    recursion_limit=recursion_limit
                )

                # Persist edited file contents so they survive a disk wipe even if a
                # full re-index never runs again before the next restart.
                if task_result.get("success") and task_result.get("edited_files") and repository_id:
                    result = await db.execute(
                        select(Repository).where(Repository.id == repository_id)
                    )
                    repository = result.scalar_one_or_none()
                    if repository:
                        repository.files = {**(repository.files or {}), **task_result["edited_files"]}
                        await db.commit()
                # The run wrote to disk (the user already has the result): re-index so later questions see the new code.
                if task_result.get("success") and task_result.get("edited_files"):
                    await refresh_repository_index(repo_path, collection_name)

            else:  # QUESTION_ANSWERING
                task_result = await task_manager.execute_question_answering(
                    session_id=session_id,
                    user_prompt=prompt,
                    repo_path=repo_path,
                    collection_name=collection_name,
                    recursion_limit=recursion_limit
                )

            # Keep what the run cost/did, for evaluation. Never raises (see run_store).
            run = await record_agent_run(
                db, session_id=session_id, mode=mode.value, prompt=prompt,
                task_result=task_result, provider=LLM_PROVIDER, model=MODEL_NAME,
            )

            result = await db.execute(select(Session).where(Session.id == session_id))
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.result = task_result
                db_session.is_active = False
                db_session.completed_at = datetime.utcnow()
                await db.commit()

            # §2.5 online evals: the user already has their result; grade a steady 1 in 10 runs. Never raises.
            if run is not None and is_sampled(run.id):
                await grade_run(db, run.id, "sample")

        except Exception as e:
            logger.error(f"Background generation task failed: {e}", exc_info=True)
            result = await db.execute(select(Session).where(Session.id == session_id))
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.result = {"success": False, "error": str(e)}
                db_session.is_active = False
                db_session.completed_at = datetime.utcnow()
                await db.commit()


@app.post("/generate")
async def start_generation(
    http_request: Request,
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a generation task (project generation, repository editing, or question answering).
    Validates the request and resolves the repo/project path synchronously,
    then schedules the actual agent run as a background task and returns
    immediately - see `_run_generation_task` for why."""
    # §3.1 guardrails: refuse oversized requests, and cap each user's agent runs per hour/day (backend/guardrails.py).
    check_prompt(request.prompt)
    await enforce_rate_limit(db, current_user["sub"])

    # Use provided session_id or generate a new one
    session_id = request.session_id if request.session_id else str(uuid.uuid4())

    # Create session record
    db_session = Session(
        id=session_id,
        user_id=current_user["sub"],
        mode=request.mode,
        project_id=request.project_id,
        repository_id=request.repository_id,
        messages=[],
        is_active=True
    )

    db.add(db_session)
    await db.commit()

    # Where a generation run writes. Only generation needs the folder, and the root is
    # set by the worker for its own run - setting it here repointed any run already
    # writing in another thread.
    project_root = f"./generated_projects/{session_id}"
    if request.mode == SessionMode.GENERATION:
        os.makedirs(project_root, exist_ok=True)

    repo_path = None
    collection_name = None

    # Resolve inputs based on mode
    if request.mode == SessionMode.GENERATION:
        # Update project status
        if request.project_id:
            result = await db.execute(
                select(Project).where(Project.id == request.project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                project.status = ProjectStatus.IN_PROGRESS
                project.error_message = None
                project.started_at = datetime.utcnow()
                await db.commit()

    elif request.mode == SessionMode.EDITING:
        if not request.repository_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository ID required for editing mode"
            )

        result = await db.execute(
            select(Repository).where(Repository.id == request.repository_id)
        )
        repository = result.scalar_one_or_none()

        if not repository:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        from agent.repository.service import ensure_repo_on_disk
        rehydrated_path = ensure_repo_on_disk(repository.local_path, repository.files, repository.id)
        if rehydrated_path != repository.local_path:
            repository.local_path = rehydrated_path
            await db.commit()

        # Determine repo path - prioritize local path for local repos
        if repository.local_path:
            repo_path = repository.local_path
        elif repository.url:
            # Clone GitHub repositories to local path if needed
            if repository.url.startswith('http'):
                from agent.repository.service import clone_github_repo, clone_dir_for
                local_repo_path = clone_dir_for(repository.name, repository.url)
                # Ensure temp_repos directory exists
                os.makedirs("./temp_repos", exist_ok=True)
                try:
                    repo_path = clone_github_repo(repository.url, local_repo_path)
                    logger.info(f"Cloned repository to: {repo_path}")
                except Exception as e:
                    logger.error(f"Failed to clone repository: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to clone repository: {str(e)}"
                    )
            else:
                repo_path = repository.url
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository URL or local path must be provided"
            )
        collection_name = repository.collection_name

    elif request.mode == SessionMode.QUESTION_ANSWERING:
        if not request.repository_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository ID required for question answering mode"
            )

        result = await db.execute(
            select(Repository).where(Repository.id == request.repository_id)
        )
        repository = result.scalar_one_or_none()

        if not repository:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        # Determine repo path - prioritize local path for local repos
        if repository.local_path:
            repo_path = repository.local_path
        elif repository.url:
            # Clone GitHub repositories to local path if needed
            if repository.url.startswith('http'):
                from agent.repository.service import clone_github_repo, clone_dir_for
                local_repo_path = clone_dir_for(repository.name, repository.url)
                try:
                    repo_path = clone_github_repo(repository.url, local_repo_path)
                except Exception as e:
                    logger.error(f"Failed to clone repository: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to clone repository: {str(e)}"
                    )
            else:
                repo_path = repository.url
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository URL or local path must be provided"
            )
        collection_name = repository.collection_name

    background_tasks.add_task(
        _run_generation_task,
        mode=request.mode,
        session_id=session_id,
        prompt=request.prompt,
        project_root=project_root,
        project_id=request.project_id,
        repository_id=request.repository_id,
        repo_path=repo_path,
        collection_name=collection_name,
        recursion_limit=request.recursion_limit
    )

    return {
        "session_id": session_id,
        "mode": request.mode,
        "status": "processing"
    }


@app.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get session information."""
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == current_user["sub"]
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return {
        "id": session.id,
        "mode": session.mode,
        "project_id": session.project_id,
        "repository_id": session.repository_id,
        "messages": session.messages,
        "result": session.result,
        "is_active": session.is_active,
        "created_at": session.created_at.isoformat(),
        "completed_at": session.completed_at.isoformat() if session.completed_at else None
    }


@app.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20
):
    """List recent sessions for the current user."""
    result = await db.execute(
        select(Session).where(Session.user_id == current_user["sub"]).order_by(Session.created_at.desc()).limit(limit)
    )
    sessions = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "mode": s.mode,
            "project_id": s.project_id,
            "repository_id": s.repository_id,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None
        }
        for s in sessions
    ]


@app.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Rate (thumbs up/down) the answer or change a session produced. Rating again replaces the rating."""
    feedback = await save_feedback(
        db, session_id=request.session_id, user_id=current_user["sub"],
        rating=request.rating, comment=request.comment,
    )
    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No finished run found for that session"
        )
    # §2.5: every thumbs-down gets graded by the judge, after the response is sent.
    if feedback.rating == "down" and ON_THUMBS_DOWN:
        background_tasks.add_task(grade_run_in_new_session, async_session, feedback.run_id, "thumbs_down")
    return {"run_id": feedback.run_id, "rating": feedback.rating}


async def require_admin(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Only users whose role is ADMIN (set directly in the database)."""
    user = await db.get(User, current_user["sub"])
    if user is None or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return current_user


@app.get("/admin/evals")
async def admin_evals(
    limit: int = Query(50, ge=1, le=200),
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """§2.5 online evals: recent judge verdicts on real runs, plus a 7-day summary per mode."""
    rows = (await db.execute(
        select(EvalResult, AgentRun).join(AgentRun, AgentRun.id == EvalResult.run_id)
        .order_by(EvalResult.created_at.desc()).limit(limit)
    )).all()
    run_ids = [run.id for _, run in rows]
    ratings = {}
    if run_ids:
        for run_id, rating in (await db.execute(select(Feedback.run_id, Feedback.rating).where(Feedback.run_id.in_(run_ids)))).all():
            ratings[run_id] = rating

    since = datetime.utcnow() - timedelta(days=7)
    recent = (await db.execute(
        select(AgentRun.mode, EvalResult.score, EvalResult.passed)
        .join(AgentRun, AgentRun.id == EvalResult.run_id).where(EvalResult.created_at >= since)
    )).all()
    summary = []
    for mode in sorted({m for m, _, _ in recent}):
        judged = [(sc, ok) for m, sc, ok in recent if m == mode and ok is not None]
        summary.append({
            "mode": mode,
            "graded": sum(1 for m, _, _ in recent if m == mode),
            "judged": len(judged),
            "avg_score": round(sum(sc or 0 for sc, _ in judged) / len(judged), 3) if judged else None,
            "pass_rate": round(sum(1 for _, ok in judged if ok) / len(judged), 3) if judged else None,
        })

    return {
        "summary": summary,
        "items": [{
            "run_id": run.id, "graded_at": ev.created_at.isoformat() if ev.created_at else None,
            "mode": run.mode, "trigger": ev.trigger, "score": ev.score, "passed": ev.passed,
            "rationale": ev.rationale, "evaluator": ev.evaluator_name, "user_rating": ratings.get(run.id),
            "prompt": (run.user_prompt or "")[:300],
        } for ev, run in rows],
    }


@app.post("/repositories/{repository_id}/edits/{session_id}/resolve")
async def resolve_edits(
    repository_id: str,
    session_id: str,
    request: EditReviewRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Accept or reject the files one editing run changed (rejecting restores the pre-edit content)."""
    from agent.repository.service import ensure_repo_on_disk

    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == current_user["sub"],
            Session.repository_id == repository_id,
        )
    )
    session = result.scalar_one_or_none()
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.user_id == current_user["sub"],
        )
    )
    repository = result.scalar_one_or_none()
    if not session or not repository or not (session.result or {}).get("edited_files"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No edits found for that session")

    repo_path = await asyncio.to_thread(
        ensure_repo_on_disk, repository.local_path, repository.files, repository.id
    )
    outcome = await asyncio.to_thread(
        apply_review, repo_path, session.result, request.accept, request.reject, request.edited
    )

    # Reassign (don't mutate): JSON columns aren't change-tracked in place.
    session.result = {**session.result, "edit_review": outcome["review"]}
    files = dict(repository.files or {})
    for path, content in outcome["files"].items():
        if content is None:
            files.pop(path, None)
        else:
            files[path] = content
    repository.files = files
    await db.commit()
    if outcome["files"]:   # a reject restored a file or an accept wrote a hand edit: the index must follow the disk
        background_tasks.add_task(refresh_repository_index, repo_path, repository.collection_name)
    return {"review": outcome["review"], "conflicts": outcome["conflicts"]}


# =========================
# WebSocket Endpoint
# =========================

# Heroku's router drops WebSocket connections idle for ~55s with no traffic,
# so the server must send its own keepalive instead of relying on the client.
WS_PING_INTERVAL_SEC = 30


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time progress updates."""
    # For now, we'll use a simple user_id from query params
    # In production, this should come from JWT token
    user_id = websocket.query_params.get("user_id", "anonymous")

    await manager.connect(websocket, session_id, user_id)

    try:
        while True:
            # Keep connection alive and handle incoming messages
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=WS_PING_INTERVAL_SEC)
            except asyncio.TimeoutError:
                # No client traffic within the interval - send a server-initiated ping
                await websocket.send_json({"type": "ping"})
                continue

            # Handle incoming messages if needed
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)


# Prometheus metrics: request-level histograms/counters plus the custom LLM
# token/cost/latency and agent-run counters registered in agent/observability.py
# (they share the default registry, so they show up on the same /metrics page).
# Called after all routes are registered so path templates are captured correctly.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# =========================
# Main Entry Point
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))