"""Structured JSON logging with per-run correlation IDs.

Configures the stdlib `logging` root logger to render every record (ours and
third-party libraries' - uvicorn, sqlalchemy, langchain, ...) as JSON via
structlog's `ProcessorFormatter`. Existing `logging.getLogger(__name__)` call
sites throughout `agent/` and `backend/` don't need to change: they get JSON
output and any context bound with `bind_run_context` for free.

Only the backend (`backend/main.py`) calls `configure_logging()` - the CLI
entrypoint (`main.py`) keeps plain `print()` output, which is what an
interactive terminal user wants.
"""
import logging
import sys

import structlog

_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure JSON structured logging for the whole process. Idempotent."""
    global _configured
    if _configured:
        return

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        # Pulls `extra={...}` kwargs passed to plain `logging.getLogger(__name__)`
        # calls (used throughout agent/ and backend/) into the JSON event dict.
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    _configured = True


def bind_run_context(**kwargs) -> None:
    """Bind correlation fields (session_id, run_id, mode, ...) to every log
    line emitted on the current thread/task until `clear_run_context()`."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_run_context() -> None:
    structlog.contextvars.clear_contextvars()
