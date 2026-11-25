"""User-facing progress from inside a graph run ("Planning the changes", "Writing app.js (2 of 3)").

The worker thread that runs a graph sets a callback for its own run; nodes call `report_progress`.
A ContextVar, like the project root in `agent.tools`, so concurrent runs never report into each
other's chat. Without a callback (CLI, evals, generation) reporting does nothing.
"""
import logging
from contextvars import ContextVar
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_reporter: ContextVar[Optional[Callable[[str], None]]] = ContextVar("progress_reporter", default=None)


def set_progress_reporter(callback: Optional[Callable[[str], None]]) -> None:
    _reporter.set(callback)


def report_progress(message: str) -> None:
    """Tell the user what the run is doing now. Never raises: progress must not break a run."""
    callback = _reporter.get()
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        logger.warning("Could not report progress", exc_info=True)
