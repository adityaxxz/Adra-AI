"""Persist finished agent runs so they can be queried and evaluated later."""
import logging
import uuid
from typing import Optional

from backend.db_models import AgentRun, RunStep

logger = logging.getLogger(__name__)


def _integration_fixes(task_result: dict) -> int:
    # project generation reports it at the top level; editing carries it in the graph state
    fixes = task_result.get("integration_fixes")
    if fixes is None:
        fixes = (task_result.get("result") or {}).get("integration_fixes")
    return int(fixes or 0)


def build_agent_run(*, session_id: str, mode: str, prompt: str, task_result: dict,
                    provider: Optional[str], model: Optional[str]) -> AgentRun:
    """Turn a `BackgroundTaskManager.execute_*` result into an (unsaved) AgentRun.

    `task_result["metrics"]` is a `RunMetrics.snapshot()`. It is absent only when a
    run died before any LLM call, in which case the token/cost columns stay zero.
    """
    metrics = task_result.get("metrics") or {}
    success = bool(task_result.get("success"))

    run = AgentRun(
        id=str(uuid.uuid4()),
        session_id=session_id,
        mode=mode,
        user_prompt=prompt,
        provider=provider,
        model=model,
        status="success" if success else "failure",
        error_message=None if success else str(task_result.get("error") or "unknown error"),
        llm_calls=metrics.get("llm_calls", 0),
        input_tokens=metrics.get("input_tokens", 0),
        output_tokens=metrics.get("output_tokens", 0),
        cost_usd=metrics.get("cost_usd", 0.0),
        latency_ms=metrics.get("latency_ms", 0.0),
        retries=metrics.get("retries", 0),
        integration_fixes=_integration_fixes(task_result),
    )
    for agent, bucket in (metrics.get("per_agent") or {}).items():
        run.steps.append(RunStep(
            id=str(uuid.uuid4()),
            agent=agent,
            calls=bucket.get("calls", 0),
            input_tokens=bucket.get("input_tokens", 0),
            output_tokens=bucket.get("output_tokens", 0),
            latency_ms=bucket.get("latency_ms", 0.0),
        ))
    return run


async def record_agent_run(db, **kwargs) -> Optional[AgentRun]:
    """Save a run. Never raises: recording is telemetry, and must not be able to
    take down the user-facing run it describes."""
    try:
        run = build_agent_run(**kwargs)
        db.add(run)
        await db.commit()
        return run
    except Exception as e:
        logger.error(f"Failed to record agent run for session {kwargs.get('session_id')!r}: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        return None
