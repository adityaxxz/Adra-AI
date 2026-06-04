from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import select
from typing import Optional, List
from pydantic import BaseModel
import os
import uuid
from datetime import datetime
import shutil

from backend.auth import (
    oauth_callback, GoogleOAuth, GitHubOAuth, get_current_user,
    Token, OAuthConfig
)
from backend.db_models import Base, User, Project, Repository, Session, SessionMode, ProjectStatus
from backend.websocket_manager import manager, ProgressReporter
from backend.background_tasks import task_manager


# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://adrai:adrai_password@localhost:5432/adrai")
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# FastAPI app
app = FastAPI(title="Adra-AI API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Database lifecycle
@app.on_event("startup")
async def startup():
    """Initialize database tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    await engine.dispose()


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


class GenerationRequest(BaseModel):
    prompt: str
    mode: SessionMode = SessionMode.GENERATION
    project_id: Optional[str] = None
    repository_id: Optional[str] = None
    recursion_limit: int = 100


# =========================
# Health Check
# =========================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# =========================
# OAuth Endpoints
# =========================

@app.get("/auth/{provider}/login")
async def oauth_login(provider: str, redirect_uri: Optional[str] = None):
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
    
    return token_data


@app.get("/auth/me")
async def get_current_user_endpoint(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return current_user


# =========================
# Projects Endpoints
# =========================

@app.post("/projects", response_model=dict)
async def create_project(
    project: ProjectCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new project."""
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
        "completed_at": project.completed_at.isoformat() if project.completed_at else None
    }


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a project."""
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
    
    await db.delete(project)
    await db.commit()
    
    return {"message": "Project deleted successfully"}


# =========================
# Repositories Endpoints
# =========================

@app.post("/repositories", response_model=dict)
async def create_repository(
    repository: RepositoryCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new repository."""
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
            "files_count": r.files_count,
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
    
    return {
        "id": repository.id,
        "name": repository.name,
        "url": repository.url,
        "local_path": repository.local_path,
        "provider": repository.provider,
        "collection_name": repository.collection_name,
        "is_indexed": repository.is_indexed,
        "files_count": repository.files_count,
        "chunks_count": repository.chunks_count,
        "created_at": repository.created_at.isoformat(),
        "updated_at": repository.updated_at.isoformat() if repository.updated_at else None,
        "last_indexed_at": repository.last_indexed_at.isoformat() if repository.last_indexed_at else None
    }


@app.post("/repositories/{repository_id}/index")
async def index_repository_endpoint(
    repository_id: str,
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Index a repository in the background."""
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
    
    # Determine repo path
    repo_path = repository.url if repository.url else repository.local_path
    
    if not repo_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository URL or local path must be provided"
        )
    
    # Start background indexing task
    task_result = await task_manager.index_repository_task(
        session_id=session_id,
        repo_path=repo_path,
        collection_name=repository.collection_name
    )
    
    # Update repository status
    if task_result["success"]:
        repository.is_indexed = True
        repository.files_count = task_result["stats"].files_indexed
        repository.chunks_count = task_result["stats"].chunks_created
        repository.last_indexed_at = datetime.utcnow()
        await db.commit()
    
    return task_result


@app.delete("/repositories/{repository_id}")
async def delete_repository(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a repository."""
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
    
    # Delete Qdrant collection
    from backend.services.vector_store import get_vector_store
    vector_store = get_vector_store()
    vector_store.clear_collection(repository.collection_name)
    
    await db.delete(repository)
    await db.commit()
    
    return {"message": "Repository deleted successfully"}


# =========================
# Generation Endpoints
# =========================

@app.post("/generate")
async def start_generation(
    request: GenerationRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a generation task (project generation, repository editing, or question answering)."""
    session_id = str(uuid.uuid4())
    
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
    
    # Determine project root for generation
    project_root = f"./generated_projects/{session_id}"
    os.makedirs(project_root, exist_ok=True)
    
    # Start appropriate task based on mode
    if request.mode == SessionMode.GENERATION:
        # Update project status
        if request.project_id:
            result = await db.execute(
                select(Project).where(Project.id == request.project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                project.status = ProjectStatus.IN_PROGRESS
                await db.commit()
        
        task_result = await task_manager.execute_project_generation(
            session_id=session_id,
            user_prompt=request.prompt,
            project_root=project_root,
            recursion_limit=request.recursion_limit
        )
        
        # Update project with results
        if task_result["success"] and request.project_id:
            result = await db.execute(
                select(Project).where(Project.id == request.project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                project.files = task_result["files"]
                project.status = ProjectStatus.COMPLETED
                project.integration_fixes = task_result.get("integration_fixes", 0)
                project.completed_at = datetime.utcnow()
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
        
        repo_path = repository.url if repository.url else repository.local_path
        task_result = await task_manager.execute_repository_editing(
            session_id=session_id,
            user_prompt=request.prompt,
            repo_path=repo_path,
            collection_name=repository.collection_name,
            recursion_limit=request.recursion_limit
        )
    
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
        
        repo_path = repository.url if repository.url else repository.local_path
        task_result = await task_manager.execute_question_answering(
            session_id=session_id,
            user_prompt=request.prompt,
            repo_path=repo_path,
            collection_name=repository.collection_name,
            recursion_limit=request.recursion_limit
        )
    
    # Update session
    db_session.result = task_result
    db_session.is_active = False
    db_session.completed_at = datetime.utcnow()
    await db.commit()
    
    return {
        "session_id": session_id,
        "mode": request.mode,
        "result": task_result
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


# =========================
# WebSocket Endpoint
# =========================

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
            data = await websocket.receive_json()
            
            # Handle incoming messages if needed
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)


# =========================
# Main Entry Point
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)