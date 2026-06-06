import asyncio
from typing import Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import uuid
from datetime import datetime
import traceback
import sys
import os

# Add the parent directory to the path so we can import the agent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.graph import project_generation_agent, repository_editing_agent, question_answering_agent
from agent.repository.service import index_repository, clone_github_repo
from backend.websocket_manager import ProgressReporter
from agent.repository.vector_store import set_active_collection


class BackgroundTaskManager:
    """Manage background task execution for agents."""
    
    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_status: Dict[str, Dict] = {}
    
    def generate_task_id(self) -> str:
        """Generate a unique task ID."""
        return str(uuid.uuid4())
    
    async def execute_project_generation(
        self,
        session_id: str,
        user_prompt: str,
        project_root: str,
        recursion_limit: int = 100
    ) -> Dict:
        """Execute project generation agent in background."""
        reporter = ProgressReporter(session_id)
        task_id = self.generate_task_id()
        
        try:
            await reporter.start(f"Starting project generation for: {user_prompt[:50]}...")
            reporter.set_total_steps(5)
            
            # Step 1: Initialize
            await reporter.step("initialization", "...")
            
            # Import and setup
            from agent.tools import set_project_root, init_project_root
            init_project_root()
            
            # Step 2: Run agent
            await reporter.step("agent_execution", "...")
            await reporter.agent_update("project_generation_agent", "started")
            
            # Run the agent in a thread pool since it's synchronous
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._run_project_generation_agent,
                user_prompt,
                recursion_limit,
                reporter
            )
            
            # Step 3: Integration fixes
            await reporter.step("integration", "...")
            fixes = result.get("integration_fixes", 0)
            if fixes:
                await reporter.update("integration", f"Applied {fixes} integration fix(es)")
            
            # Step 4: Collect files
            await reporter.step("collecting_files", "...")
            files = self._collect_project_files(project_root)
            
            # Step 5: Complete
            await reporter.step("complete", "...")
            await reporter.agent_update("project_generation_agent", "completed")
            
            return {
                "success": True,
                "result": result,
                "files": files,
                "integration_fixes": fixes,
                "task_id": task_id
            }
            
        except Exception as e:
            await reporter.error(f"Project generation failed: {str(e)}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id
            }
    
    def _run_project_generation_agent(
        self,
        user_prompt: str,
        recursion_limit: int,
        reporter: ProgressReporter
    ) -> Dict:
        """Synchronous wrapper for project generation agent."""
        try:
            agent = project_generation_agent
            initial_state = {"user_prompt": user_prompt}
            
            result = agent.invoke(
                initial_state,
                {"recursion_limit": recursion_limit}
            )
            
            return result
        except Exception as e:
            print(f"Error in project generation agent: {e}")
            raise
    
    async def execute_repository_editing(
        self,
        session_id: str,
        user_prompt: str,
        repo_path: str,
        collection_name: str,
        recursion_limit: int = 100
    ) -> Dict:
        """Execute repository editing agent in background."""
        reporter = ProgressReporter(session_id)
        task_id = self.generate_task_id()
        
        try:
            await reporter.start(f"Starting repository editing for: {user_prompt[:50]}...")
            reporter.set_total_steps(5)
            
            # Step 1: Setup
            await reporter.step("setup", "...")
            from agent.tools import set_project_root
            set_project_root(repo_path)
            set_active_collection(collection_name)
            
            # Step 2: Index if needed
            await reporter.step("indexing", "...")
            # Indexing is assumed to be done beforehand
            
            # Step 3: Run agent
            await reporter.step("agent_execution", "...")
            await reporter.agent_update("repository_editing_agent", "started")
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._run_repository_editing_agent,
                user_prompt,
                repo_path,
                collection_name,
                recursion_limit
            )
            
            # Step 4: Collect changes
            await reporter.step("collecting_changes", "...")
            changes = result.get("changes", {})
            
            # Step 5: Complete
            await reporter.step("complete", "...")
            await reporter.agent_update("repository_editing_agent", "completed")
            
            return {
                "success": True,
                "result": result,
                "changes": changes,
                "task_id": task_id
            }
            
        except Exception as e:
            await reporter.error(f"Repository editing failed: {str(e)}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id
            }
    
    def _run_repository_editing_agent(
        self,
        user_prompt: str,
        repo_path: str,
        collection_name: str,
        recursion_limit: int
    ) -> Dict:
        """Synchronous wrapper for repository editing agent."""
        try:
            agent = repository_editing_agent
            initial_state = {
                "user_prompt": user_prompt,
                "repo_path": repo_path,
                "collection_name": collection_name
            }
            
            result = agent.invoke(
                initial_state,
                {"recursion_limit": recursion_limit}
            )
            
            return result
        except Exception as e:
            print(f"Error in repository editing agent: {e}")
            raise
    
    async def execute_question_answering(
        self,
        session_id: str,
        user_prompt: str,
        repo_path: str,
        collection_name: str,
        recursion_limit: int = 100
    ) -> Dict:
        """Execute question answering agent in background."""
        reporter = ProgressReporter(session_id)
        task_id = self.generate_task_id()
        
        try:
            await reporter.start(f"Processing question: {user_prompt[:50]}...")
            reporter.set_total_steps(4)
            
            # Step 1: Setup
            await reporter.step("setup", "...")
            from agent.tools import set_project_root
            from pathlib import Path
            
            # Check if repo_path exists
            if not Path(repo_path).exists():
                error_msg = f"Repository path does not exist: {repo_path}"
                print(error_msg)
                await reporter.error(error_msg)
                return {"success": False, "error": error_msg, "task_id": task_id}
            
            set_project_root(repo_path)
            set_active_collection(collection_name)
            print(f"Question answering setup complete for: {repo_path}")
            
            # Step 2: Search relevant code
            await reporter.step("searching", "...")
            
            # Step 3: Run agent
            await reporter.step("agent_execution", "Running question answering agent")
            await reporter.agent_update("question_answering_agent", "started")
            
            print(f"Starting question answering agent with prompt: {user_prompt}")
            print(f"Repository path: {repo_path}")
            print(f"Collection name: {collection_name}")
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._run_question_answering_agent,
                user_prompt,
                repo_path,
                collection_name,
                recursion_limit
            )
            
            print(f"Question answering agent completed. Result: {result}")
            
            # Step 4: Complete
            await reporter.step("complete", "...")
            await reporter.agent_update("question_answering_agent", "completed")
            
            answer = result.get("answer", "No answer generated")
            print(f"Question answering result: {result}")
            print(f"Extracted answer: {answer}")
            print(f"Answer length: {len(answer) if answer else 0}")
            
            # Send the answer via WebSocket
            await reporter.complete({"answer": answer, "message": answer})
            
            return {
                "success": True,
                "result": result,
                "answer": answer,
                "task_id": task_id
            }
            
        except Exception as e:
            await reporter.error(f"Question answering failed: {str(e)}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id
            }
    
    def _run_question_answering_agent(
        self,
        user_prompt: str,
        repo_path: str,
        collection_name: str,
        recursion_limit: int
    ) -> Dict:
        """Synchronous wrapper for question answering agent."""
        try:
            agent = question_answering_agent
            initial_state = {
                "user_prompt": user_prompt,
                "repo_path": repo_path,
                "collection_name": collection_name
            }
            
            result = agent.invoke(
                initial_state,
                {"recursion_limit": recursion_limit}
            )
            
            return result
        except Exception as e:
            print(f"Error in question answering agent: {e}")
            raise
    
    async def index_repository_task(
        self,
        session_id: str,
        repo_path: str,
        collection_name: str
    ) -> Dict:
        """Index repository in background with progress updates."""
        reporter = ProgressReporter(session_id)
        task_id = self.generate_task_id()
        
        try:
            await reporter.start(f"Indexing repository: {repo_path}")
            reporter.set_total_steps(4)
            
            # Step 1: Scan files
            await reporter.step("scanning", "Scanning repository files")
            
            # Step 2: Chunk files
            await reporter.step("chunking", "Processing and chunking files")
            
            # Step 3: Generate embeddings
            await reporter.step("embedding", "Generating embeddings")
            
            # Step 4: Index in Qdrant
            await reporter.step("indexing", "Indexing in vector database")
            
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(
                self.executor,
                index_repository,
                repo_path,
                collection_name
            )
            
            await reporter.step("complete", f"Indexing completed: {stats.files_indexed} files indexed")
            
            return {
                "success": True,
                "stats": stats,
                "task_id": task_id
            }
            
        except Exception as e:
            await reporter.error(f"Repository indexing failed: {str(e)}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id
            }
    
    def _collect_project_files(self, project_root: str) -> Dict[str, str]:
        """Collect all files from a generated project."""
        import os
        files = {}
        
        try:
            for root, dirs, filenames in os.walk(project_root):
                # Skip hidden directories and common exclusions
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv']]
                
                for filename in filenames:
                    if not filename.startswith('.'):
                        file_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(file_path, project_root)
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                files[relative_path] = f.read()
                        except (UnicodeDecodeError, IOError):
                            # Skip binary files or files that can't be read
                            files[relative_path] = None
            
            return files
        except Exception as e:
            print(f"Error collecting project files: {e}")
            return {}
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status of a background task."""
        return self.task_status.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a background task."""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            if not task.done():
                task.cancel()
                self.task_status[task_id] = {
                    "status": "cancelled",
                    "cancelled_at": datetime.utcnow().isoformat()
                }
                return True
        return False


# Global task manager instance
task_manager = BackgroundTaskManager()
