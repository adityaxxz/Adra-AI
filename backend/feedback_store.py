"""Save a user's rating of a finished agent run."""
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db_models import AgentRun, Feedback, Session

RATINGS = ("up", "down")


async def _find_run_id(db, session_id: str, user_id: str) -> Optional[str]:
    """The run recorded for this session, only if the session belongs to `user_id`.

    The chat creates one session per message, so a session has one run; if it ever has several,
    the latest is the one the user just saw."""
    result = await db.execute(
        select(AgentRun.id)
        .join(Session, Session.id == AgentRun.session_id)
        .where(AgentRun.session_id == session_id, Session.user_id == user_id)
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _existing(db, run_id: str, user_id: str) -> Optional[Feedback]:
    result = await db.execute(select(Feedback).where(Feedback.run_id == run_id, Feedback.user_id == user_id))
    return result.scalar_one_or_none()


async def save_feedback(db, *, session_id: str, user_id: str, rating: str, comment: Optional[str] = None) -> Optional[Feedback]:
    """Create or replace `user_id`'s rating of the run behind `session_id`.

    Returns None when there is nothing to rate: no such session for this user (the same answer for "not
    yours" as for "doesn't exist"), or its run was not recorded (yet, or recording failed)."""
    if rating not in RATINGS:
        raise ValueError(f"rating must be one of {RATINGS}")
    comment = (comment or "").strip() or None

    run_id = await _find_run_id(db, session_id, user_id)
    if run_id is None:
        return None

    for _ in range(2):  # a double-click can race two inserts past the unique constraint; the second pass updates
        feedback = await _existing(db, run_id, user_id)
        if feedback is None:
            feedback = Feedback(id=str(uuid.uuid4()), run_id=run_id, user_id=user_id)
            db.add(feedback)
        feedback.rating, feedback.comment = rating, comment
        try:
            await db.commit()
            return feedback
        except IntegrityError:
            await db.rollback()
    raise RuntimeError("could not save feedback")
