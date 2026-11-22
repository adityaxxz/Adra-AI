import io
import json
import logging

import pytest

from agent import logging_config as LC


@pytest.fixture
def captured():
    """Run configure_logging() against a buffer, then restore the root logger so
    it doesn't break pytest's own log capture for later tests."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level, LC._configured)
    LC._configured = False
    LC.configure_logging(logging.INFO)
    buf = io.StringIO()
    root.handlers[0].stream = buf
    try:
        yield lambda: [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]
    finally:
        LC.clear_run_context()
        root.handlers, root.level = saved[0], saved[1]
        LC._configured = saved[2]


def test_every_record_is_valid_json_with_standard_fields(captured):
    logging.getLogger("unit.test").info("hello")
    (rec,) = captured()
    assert rec["event"] == "hello" and rec["level"] == "info" and rec["logger"] == "unit.test"
    assert "timestamp" in rec


def test_bound_run_context_is_attached_then_dropped(captured):
    log = logging.getLogger("unit.test")
    LC.bind_run_context(session_id="sess-9", mode="qa")
    log.info("during")
    LC.clear_run_context()
    log.info("after")
    during, after = captured()
    assert during["session_id"] == "sess-9" and during["mode"] == "qa"
    assert "session_id" not in after


def test_extra_fields_are_kept(captured):
    # needs structlog's ExtraAdder - without it these were silently dropped
    logging.getLogger("unit.test").info("llm_call", extra={"tokens": 5, "agent": "coder"})
    (rec,) = captured()
    assert rec["tokens"] == 5 and rec["agent"] == "coder"


def test_exceptions_include_the_traceback(captured):
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("unit.test").error("failed", exc_info=True)
    (rec,) = captured()
    assert "ValueError: boom" in rec["exception"]


def test_sqlalchemy_statements_and_parameters_are_not_logged(captured):
    # echo=True used to log every statement *with bound parameters* - which included
    # generated source code and Q&A answers - in plaintext. A real engine, echo off:
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite://", echo=False)
    with engine.connect() as conn:
        conn.execute(text("SELECT :p AS x"), {"p": "USER-SOURCE-CODE-OR-ANSWER"})
    out = captured()
    assert not [r for r in out if r["logger"].startswith("sqlalchemy")]
    assert "USER-SOURCE-CODE-OR-ANSWER" not in str(out)
