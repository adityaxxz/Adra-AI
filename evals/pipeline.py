"""The system under test. `LivePipeline` drives the same `BackgroundTaskManager.execute_*`
methods the API uses (real graphs, real LLM, real Qdrant), minus the WebSocket and database.

Kept behind a tiny interface so the runner can be tested with a fake that needs no network.
"""
import asyncio
from pathlib import Path


class LivePipeline:
    def __init__(self, recursion_limit: int = 60):
        # Imported lazily: these construct the production LLM client, which needs real API keys.
        from backend.background_tasks import task_manager

        self.tm = task_manager
        self.recursion_limit = recursion_limit

    def generate(self, case: dict, workdir: Path, session_id: str) -> dict:
        from agent.tools import set_project_root

        set_project_root(str(workdir))
        return asyncio.run(self.tm.execute_project_generation(
            session_id=session_id, user_prompt=case["prompt"], project_root=str(workdir), recursion_limit=self.recursion_limit))

    def edit(self, case: dict, workdir: Path, session_id: str, collection: str) -> dict:
        return asyncio.run(self.tm.execute_repository_editing(
            session_id=session_id, user_prompt=case["prompt"], repo_path=str(workdir),
            collection_name=collection, recursion_limit=self.recursion_limit))

    def answer(self, case: dict, workdir: Path, session_id: str, collection: str) -> dict:
        return asyncio.run(self.tm.execute_question_answering(
            session_id=session_id, user_prompt=case["prompt"], repo_path=str(workdir),
            collection_name=collection, recursion_limit=self.recursion_limit))

    def index(self, fixture_dir: Path, collection: str) -> None:
        from agent.repository.service import index_repository

        index_repository(str(fixture_dir), collection_name=collection, reset=True)

    def retrieve(self, question: str, collection: str, k: int) -> list[tuple[str, str]]:
        """The chunks the agent's own retrieval step sees for this question: [(file_path, content)]."""
        from agent.repository.retriever import retrieve

        return [(r.file_path, r.content) for r in retrieve(question, k=k, collection_name=collection)]

    def cleanup(self, collections: list[str]) -> None:
        from agent.repository.vector_store import clear_collection

        for c in collections:
            try:
                clear_collection(c)
            except Exception:                              # noqa: BLE001 - best effort
                pass

    def describe(self) -> dict:
        from agent.llm_client import LLM_PROVIDER, MODEL_NAME

        return {"provider": LLM_PROVIDER, "model": MODEL_NAME}
