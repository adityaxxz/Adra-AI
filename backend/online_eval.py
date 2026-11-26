"""Online evals for §2.5 "Online evals + feedback loop": grade real runs with the LLM judge.

Graded: a steady 1 in 10 successful runs (picked from the run id, so the choice is reproducible), plus every run a user
rates thumbs-down. Grading happens after the user already has their result and never raises: a judge failure must not
affect the run it is grading. Scores are for the owner (admin page); they are never shown to users.
"""
import asyncio
import hashlib
import logging
import os
import uuid
from typing import Callable, Optional

from sqlalchemy import select

from backend.db_models import AgentRun, EvalResult, Repository, Session

logger = logging.getLogger(__name__)

SAMPLE_RATE = float(os.getenv("ONLINE_EVAL_SAMPLE_RATE", "0.1"))           # 0 turns sampling off
ON_THUMBS_DOWN = os.getenv("ONLINE_EVAL_ON_THUMBS_DOWN", "true").strip().lower() not in ("0", "false", "no", "off")
MAX_RATIONALE_CHARS = 4000

_judge = None


def get_judge():
    """One shared judge, so its pacing (free tier: 15 requests/minute) and quota breaker cover every request."""
    global _judge
    if _judge is None:
        from evals.evaluators.judge import Judge

        _judge = Judge()
    return _judge


def is_sampled(run_id: str, rate: Optional[float] = None) -> bool:
    """Deterministic: the same run is always in or out, and about `rate` of all runs are in."""
    rate = SAMPLE_RATE if rate is None else rate
    if rate <= 0:
        return False
    bucket = int(hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return bucket < rate


def _default_retrieve(question: str, collection: str) -> str:
    from agent.repository.service import search_repository

    return "\n\n".join(f"FILE: {r.file_path}\n\n{r.content}" for r in search_repository(question, collection_name=collection))


async def grade_run(db, run_id: str, trigger: str, *, judge=None, retrieve: Optional[Callable[[str, str], str]] = None) -> Optional[EvalResult]:
    """Judge one finished run and store the verdict. Returns the stored (or already existing) result, or None when
    there is nothing to grade (unknown or failed run) or grading failed. Never raises."""
    try:
        run = await db.get(AgentRun, run_id)
        if run is None or run.status != "success":
            return None
        judge = judge or get_judge()
        evaluator = f"judge:{judge.model}"
        existing = (await db.execute(select(EvalResult).where(
            EvalResult.run_id == run_id, EvalResult.evaluator_name == evaluator))).scalar_one_or_none()
        if existing is not None:
            return existing                       # one verdict per run per judge (a sampled run later rated down isn't re-graded)

        session = await db.get(Session, run.session_id)
        result = (session.result or {}) if session else {}
        case = {"id": f"run:{run_id}", "mode": run.mode, "prompt": run.user_prompt}

        if run.mode == "question_answering":
            context = ""
            if session and session.repository_id:
                repo = await db.get(Repository, session.repository_id)
                if repo is not None:
                    context = await asyncio.to_thread(retrieve or _default_retrieve, run.user_prompt, repo.collection_name)
            outcome = await asyncio.to_thread(judge.judge_answer, case, result.get("answer") or "", context)
        elif run.mode == "editing":
            before = result.get("original_files") or {}
            after = {**before, **(result.get("edited_files") or {})}
            outcome = await asyncio.to_thread(judge.judge_code, case, after, before)
        else:
            outcome = await asyncio.to_thread(judge.judge_code, case, result.get("files") or {}, None)

        stored = EvalResult(
            id=str(uuid.uuid4()), run_id=run_id, evaluator_name=evaluator, trigger=trigger,
            score=outcome.score, passed=outcome.passed, rationale=(outcome.detail or "")[:MAX_RATIONALE_CHARS],
        )
        db.add(stored)
        await db.commit()
        return stored
    except Exception as e:                        # noqa: BLE001 - grading is telemetry; it must never break anything
        logger.error(f"online eval of run {run_id!r} ({trigger}) failed: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:                         # noqa: BLE001
            pass
        return None


async def grade_run_in_new_session(session_factory, run_id: str, trigger: str) -> None:
    """For background tasks that run after the request's DB session is closed."""
    async with session_factory() as db:
        await grade_run(db, run_id, trigger)
