"""Request guardrails for §3.1 "Guardrails (input & output)": a size cap and per-user limits on agent runs.

Every agent request (a chat question, an edit, a new project) creates one `Session` row, so the limits count a user's
recent sessions in the database. That survives dyno restarts and needs no Redis. Limits are per logged-in user, not per
IP: behind Heroku's router every request arrives from an internal address, so per-IP limits would lump all users together.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select

from backend.db_models import Session

MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "8000"))
LIMIT_PER_HOUR = int(os.getenv("GENERATION_LIMIT_PER_HOUR", "20"))     # 0 = no hourly limit
LIMIT_PER_DAY = int(os.getenv("GENERATION_LIMIT_PER_DAY", "40"))       # 0 = no daily limit


def check_prompt(prompt: str, max_chars: Optional[int] = None) -> None:
    """Refuse requests too long to be worth their token cost, with a message the user can act on."""
    limit = MAX_PROMPT_CHARS if max_chars is None else max_chars
    if limit > 0 and len(prompt) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Your request is {len(prompt):,} characters long; the limit is {limit:,}. Please shorten it and try again.",
        )


def _wait_text(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = round(minutes / 60)
    return f"{hours} hour{'s' if hours != 1 else ''}"


async def enforce_rate_limit(db, user_id: str, *, per_hour: Optional[int] = None, per_day: Optional[int] = None,
                             now: Optional[datetime] = None) -> None:
    """Raise 429 (with Retry-After) if the user already made `per_hour` agent requests in the last hour or `per_day` in
    the last 24 hours. Sliding windows: a slot frees up exactly one hour/day after the request that used it."""
    now = now or datetime.now(timezone.utc)
    windows = ((timedelta(hours=1), LIMIT_PER_HOUR if per_hour is None else per_hour, "hour"),
               (timedelta(days=1), LIMIT_PER_DAY if per_day is None else per_day, "day"))
    for span, limit, label in windows:
        if limit <= 0:
            continue
        since = now - span
        count = (await db.execute(select(func.count()).select_from(Session).where(
            Session.user_id == user_id, Session.created_at >= since))).scalar_one()
        if count < limit:
            continue
        # The slot that frees up first belongs to the oldest request still inside the window.
        oldest = (await db.execute(select(Session.created_at).where(
            Session.user_id == user_id, Session.created_at >= since).order_by(Session.created_at.desc())
            .offset(limit - 1).limit(1))).scalar_one()
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        retry_after = max(1, int((oldest + span - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached the limit of {limit} requests per {label}. Please try again in {_wait_text(retry_after)}.",
            headers={"Retry-After": str(retry_after)},
        )
