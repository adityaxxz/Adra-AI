import sys
import os
from typing import Dict, Optional, List
from datetime import datetime
import uuid


# Integration layer for connecting existing agent pipeline with database storage. This module bridges the gap between the original CLI-based agents and the new SaaS architecture.

# Add parent directory to path for importing agent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.graph import project_generation_agent, repository_editing_agent, question_answering_agent
from agent.repository.service import index_repository, clone_github_repo
from agent.tools import set_project_root, init_project_root
from agent.repository.vector_store import set_active_collection

from backend.db_models import Project, Repository, Session, SessionMode, ProjectStatus
from backend.services.vector_store import get_vector_store


class AgentIntegration:
    """Integrates existing agent pipeline with database storage."""
    
    def __init__(self, db_session):
        self.db = db_session
        self.vector_store = get_vector_store()
    
    async def create_project_from_generation(
        self,
        user_id: str,
        name: str,
        description: str,
        prompt: str,
        session_id: str
    ) -> Project:
        """Create a new project from project generation agent."""
        project_id = str(uuid.uuid4())
        
        # Create project record
        project = Project(
            id=project_id,
            user_id=user_id,
            name=name,
            description=description,
            prompt=prompt,
            files={},
            status=ProjectStatus.PENDING
        )
        
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        
        # Initialize project root
        project_root = f"./generated_projects/{project_id}"
        os.makedirs(project_root, exist_ok=True)
        set_project_root(project_root)
        
        return project
    
    async def update_project_with_files(
        self,
        project_id: str,
        files: Dict[str, str],
        status: ProjectStatus = ProjectStatus.COMPLETED,
        error_message: Optional[str] = None,
        integration_fixes: int = 0
    ) -> Project:
        """Update project with generated files and status."""
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        
        if project:
            project.files = files
            project.status = status
            if error_message:
                project.error_message = error_message
            project.integration_fixes = integration_fixes
            
            if status == ProjectStatus.COMPLETED:
                project.completed_at = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(project)
        
        return project
    
    async def create_repository_from_url(
        self,
        user_id: str,
        name: str,
        url: str,
        provider: str = "github"
    ) -> Repository:
        """Create repository record from GitHub URL."""
        repo_id = str(uuid.uuid4())
        collection_name = f"repo_{repo_id.replace('-', '_')}"
        
        repository = Repository(
            id=repo_id,
            user_id=user_id,
            name=name,
            url=url,
            provider=provider,
            collection_name=collection_name,
            is_indexed=False
        )
        
        self.db.add(repository)
        await self.db.commit()
        await self.db.refresh(repository)
        
        return repository
    
    async def create_repository_from_local(
        self,
        user_id: str,
        name: str,
        local_path: str
    ) -> Repository:
        """Create repository record from local path."""
        repo_id = str(uuid.uuid4())
        collection_name = f"repo_{repo_id.replace('-', '_')}"
        
        repository = Repository(
            id=repo_id,
            user_id=user_id,
            name=name,
            local_path=local_path,
            provider="local",
            collection_name=collection_name,
            is_indexed=False
        )
        
        self.db.add(repository)
        await self.db.commit()
        await self.db.refresh(repository)
        
        return repository
    
    async def index_repository_with_stats(
        self,
        repository_id: str,
        repo_path: str
    ) -> Dict:
        """Index repository and update with statistics."""
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repository = result.scalar_one_or_none()
        
        if not repository:
            raise ValueError(f"Repository {repository_id} not found")
        
        # Set active collection
        set_active_collection(repository.collection_name)
        
        # Index repository
        stats = index_repository(repo_path, collection_name=repository.collection_name)
        
        # Update repository with stats
        repository.is_indexed = True
        repository.files_count = stats.files_indexed
        repository.chunks_count = stats.chunks_created
        repository.last_indexed_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(repository)
        
        return {
            "repository_id": repository_id,
            "collection_name": repository.collection_name,
            "files_indexed": stats.files_indexed,
            "chunks_created": stats.chunks_created,
            "files_skipped": stats.files_skipped,
            "files_deleted": stats.files_deleted
        }
    
    async def create_session(
        self,
        user_id: str,
        mode: SessionMode,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None
    ) -> Session:
        """Create a new session for agent interaction."""
        session_id = str(uuid.uuid4())
        
        session = Session(
            id=session_id,
            user_id=user_id,
            mode=mode,
            project_id=project_id,
            repository_id=repository_id,
            messages=[],
            is_active=True
        )
        
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        
        return session
    
    async def add_message_to_session(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> Session:
        """Add a message to the session history."""
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if session:
            if not session.messages:
                session.messages = []
            
            session.messages.append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await self.db.commit()
            await self.db.refresh(session)
        
        return session
    
    async def update_session_result(
        self,
        session_id: str,
        result: Dict,
        is_active: bool = False
    ) -> Session:
        """Update session with agent result."""
        from sqlalchemy import select
        
        result_obj = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result_obj.scalar_one_or_none()
        
        if session:
            session.result = result
            session.is_active = is_active
            
            if not is_active:
                session.completed_at = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(session)
        
        return session
    
    async def get_repository_context(self, repository_id: str) -> Dict:
        """Get repository context for agent execution."""
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repository = result.scalar_one_or_none()
        
        if not repository:
            raise ValueError(f"Repository {repository_id} not found")
        
        # Determine repo path - prioritize local path for local repos
        if repository.local_path:
            repo_path = repository.local_path
        elif repository.url:
            # Clone GitHub repositories to local path if needed
            if repository.url.startswith('http'):
                repo_name = repository.url.split('/')[-1].replace('.git', '')
                local_repo_path = f"./temp_repos/{repo_name}"
                # Ensure temp_repos directory exists
                os.makedirs("./temp_repos", exist_ok=True)
                try:
                    repo_path = clone_github_repo(repository.url, local_repo_path)
                    print(f"Cloned repository to: {repo_path}")
                except Exception as e:
                    print(f"Failed to clone repository: {e}")
                    raise ValueError(f"Failed to clone repository: {str(e)}")
            else:
                repo_path = repository.url
        else:
            raise ValueError("Repository URL or local path must be provided")
        
        return {
            "repository_id": repository.id,
            "name": repository.name,
            "repo_path": repo_path,
            "collection_name": repository.collection_name,
            "is_indexed": repository.is_indexed
        }
    
    async def setup_repository_for_agent(self, repository_id: str) -> Dict:
        """Setup repository context for agent execution."""
        context = await self.get_repository_context(repository_id)
        
        # Set project root
        set_project_root(context["repo_path"])
        
        # Set active collection
        set_active_collection(context["collection_name"])
        
        return context
    
    async def get_project_files(self, project_id: str) -> Dict[str, str]:
        """Get project files from database."""
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        
        if project:
            return project.files or {}
        
        return {}
    
    async def export_project_files(
        self,
        project_id: str,
        export_path: str
    ) -> bool:
        """Export project files to filesystem."""
        import os
        
        files = await self.get_project_files(project_id)
        
        if not files:
            return False
        
        # Create export directory
        os.makedirs(export_path, exist_ok=True)
        
        # Write files
        for file_path, content in files.items():
            full_path = os.path.join(export_path, file_path)
            
            # Create directory structure
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Write file
            if content is not None:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
        
        return True