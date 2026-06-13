from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List
from pydantic import BaseModel, ValidationError
import os
import uuid
from datetime import datetime
from slowapi.errors import RateLimitExceeded
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import zipfile
import io
import shutil
import logging
import tempfile
import traceback

from backend.auth import (
    oauth_callback, GoogleOAuth, GitHubOAuth, get_current_user,
    Token, OAuthConfig
)
from backend.db_models import Base, User, Project, Repository, Session, SessionMode, ProjectStatus
from backend.websocket_manager import manager, ProgressReporter
from backend.background_tasks import task_manager
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
from agent.tools import set_project_root


# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://adrai:adrai_password@localhost:5432/adrai")
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
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
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


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
# @limiter.limit(RATE_LIMITS["api"])  # TEMPORARILY DISABLED FOR TESTING
async def create_project(
    request: Request,
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
    print(f"Delete request for project: {project_id}")
    
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user["sub"]
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        print(f"Project not found: {project_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    print(f"Deleting project: {project.name}")
    
    try:
        # First, delete all sessions that reference this project
        # This resolves the foreign key constraint issue
        sessions_result = await db.execute(
            select(Session).where(Session.project_id == project_id)
        )
        sessions = sessions_result.scalars().all()
        print(f"Found {len(sessions)} sessions to delete")
        
        for session in sessions:
            await db.delete(session)
            print(f"Deleted session: {session.id}")
        
        await db.commit()
        
        # Now delete the project
        await db.delete(project)
        await db.commit()
        
        print(f"Project deleted successfully: {project_id}")
        return {"message": "Project deleted successfully"}
    except Exception as e:
        print(f"Error deleting project: {str(e)}")
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
            "Content-Disposition": f"attachment; filename={project.name}-project.zip"
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
        "last_indexed_at": repository.last_indexed_at.isoformat() if repository.last_indexed_at else None,
        "files": files
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
    
    # Determine repo path - prioritize local path for local repos
    if repository.local_path:
        repo_path = repository.local_path
    elif repository.url:
        # Clone GitHub repositories to local path if needed
        if repository.url.startswith('http'):
            from agent.repository.service import clone_github_repo
            repo_name = repository.url.split('/')[-1].replace('.git', '')
            local_repo_path = f"./temp_repos/{repo_name}"
            # Ensure temp_repos directory exists
            os.makedirs("./temp_repos", exist_ok=True)
            try:
                repo_path = clone_github_repo(repository.url, local_repo_path)
                print(f"Cloned repository to: {repo_path}")
                # Update the repository's local_path in the database
                repository.local_path = repo_path
                await db.commit()
            except Exception as e:
                print(f"Failed to clone repository: {e}")
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
    
    # Start background indexing task
    try:
        task_result = await task_manager.index_repository_task(
            session_id=session_id,
            repo_path=repo_path,
            collection_name=repository.collection_name
        )
    except Exception as e:
        print(f"Error during indexing task: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {str(e)}"
        )
    
    # Update repository status
    if task_result["success"]:
        repository.is_indexed = True
        repository.files_count = task_result["stats"].files_indexed
        repository.chunks_count = task_result["stats"].chunks_created
        repository.last_indexed_at = datetime.utcnow()
        await db.commit()
    else:
        # Return the error from the background task
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=task_result.get("error", "Indexing failed")
        )
    
    return task_result


@app.delete("/repositories/{repository_id}")
async def delete_repository(
    repository_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a repository."""
    print(f"Delete request for repository: {repository_id}")
    
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repository = result.scalar_one_or_none()
    
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found"
        )
    
    print(f"Deleting repository: {repository.name}")
    print(f"Local path: {repository.local_path}")
    print(f"Collection name: {repository.collection_name}")
    
    try:
        # First, delete all sessions that reference this repository
        # This resolves the foreign key constraint issue
        sessions_result = await db.execute(
            select(Session).where(Session.repository_id == repository_id)
        )
        sessions = sessions_result.scalars().all()
        print(f"Found {len(sessions)} sessions to delete")
        
        for session in sessions:
            await db.delete(session)
            print(f"Deleted session: {session.id}")
        
        await db.commit()
        
        # Delete Qdrant collection if exists
        from backend.services.vector_store import get_vector_store
        vector_store = get_vector_store()
        try:
            vector_store.clear_collection(repository.collection_name)
            print(f"Cleared collection: {repository.collection_name}")
        except Exception as e:
            print(f"Failed to clear collection: {e}")
        
        # Delete uploaded files if they exist
        if repository.local_path and repository.provider == 'local':
            try:
                import shutil
                if os.path.exists(repository.local_path):
                    shutil.rmtree(repository.local_path)
                    print(f"Deleted local files: {repository.local_path}")
            except Exception as e:
                print(f"Failed to delete local files: {e}")
        
        # Delete repository from database
        await db.delete(repository)
        await db.commit()
        
        print("Repository deleted successfully")
        
        return {"message": "Repository deleted successfully"}
    except Exception as e:
        print(f"Error deleting repository: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete repository: {str(e)}"
        )
    
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


@app.post("/upload-folder")
async def upload_folder(
    files: List[UploadFile] = File(...),
    repository_name: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a local folder and create a repository."""
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
        
        repository = Repository(
            id=repo_id,
            user_id=current_user["sub"],
            name=repository_name,
            local_path=upload_dir,
            provider="local",
            collection_name=collection_name,
            is_indexed=False
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

@app.post("/generate")
# @limiter.limit(RATE_LIMITS["generation"])  # TEMPORARILY DISABLED FOR TESTING
async def start_generation(
    http_request: Request,
    request: GenerationRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a generation task (project generation, repository editing, or question answering)."""
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
    
    # Determine project root for generation
    project_root = f"./generated_projects/{session_id}"
    os.makedirs(project_root, exist_ok=True)
    set_project_root(project_root)
    
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
        
        # Determine repo path - prioritize local path for local repos
        if repository.local_path:
            repo_path = repository.local_path
        elif repository.url:
            # Clone GitHub repositories to local path if needed
            if repository.url.startswith('http'):
                from agent.repository.service import clone_github_repo
                repo_name = repository.url.split('/')[-1].replace('.git', '')
                local_repo_path = f"./temp_repos/{repo_name}"
                # Ensure temp_repos directory exists
                os.makedirs("./temp_repos", exist_ok=True)
                try:
                    repo_path = clone_github_repo(repository.url, local_repo_path)
                    print(f"Cloned repository to: {repo_path}")
                except Exception as e:
                    print(f"Failed to clone repository: {e}")
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
        
        # Determine repo path - prioritize local path for local repos
        if repository.local_path:
            repo_path = repository.local_path
        elif repository.url:
            # Clone GitHub repositories to local path if needed
            if repository.url.startswith('http'):
                from agent.repository.service import clone_github_repo
                repo_name = repository.url.split('/')[-1].replace('.git', '')
                local_repo_path = f"./temp_repos/{repo_name}"
                try:
                    repo_path = clone_github_repo(repository.url, local_repo_path)
                except Exception as e:
                    print(f"Failed to clone repository: {e}")
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