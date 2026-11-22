"""LLM client behaviour with the model itself faked: retry rules, the provider
`include_raw` gate, token truncation, and the trace configs."""
import pytest
from pydantic import BaseModel

from agent import llm_client as L
from agent import observability as O


class Out(BaseModel):
    value: str


class FakeRunnable:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def invoke(self, prompt, config=None):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    monkeypatch.setattr(L, "_throttle", lambda extra_wait=0.0: None)
    yield
    O.current_run.set(None)


class FakeLLM:
    """Replaces the module-level `llm` (a pydantic model, so its methods can't be patched in place)."""

    def __init__(self, runnable=None, record_kwargs=None, invoke=None):
        self._runnable, self._record, self._invoke = runnable, record_kwargs, invoke

    def with_structured_output(self, schema, **kw):
        if self._record is not None:
            self._record.update(kw)
        return self._runnable

    def invoke(self, prompt, config=None):
        return self._invoke(prompt, config)


def _patch_structured(monkeypatch, runnable, record_kwargs=None):
    monkeypatch.setattr(L, "llm", FakeLLM(runnable=runnable, record_kwargs=record_kwargs))


def test_structured_invoke_retries_a_transient_failure_then_succeeds(monkeypatch):
    run = O.start_run("s")
    r = FakeRunnable([ValueError("bad json"), {"raw": None, "parsed": Out(value="ok"), "parsing_error": None}])
    _patch_structured(monkeypatch, r)
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", True)
    assert L.structured_invoke(Out, "p", agent="planner").value == "ok"
    assert r.calls == 2 and run.snapshot()["retries"] == 1


def test_rate_limit_errors_are_raised_immediately_without_retrying(monkeypatch):
    r = FakeRunnable([RuntimeError("429 Too Many Requests"), {"raw": None, "parsed": Out(value="never"), "parsing_error": None}])
    _patch_structured(monkeypatch, r)
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", True)
    with pytest.raises(RuntimeError, match="429"):
        L.structured_invoke(Out, "p")
    assert r.calls == 1


def test_gives_up_after_max_retries(monkeypatch):
    r = FakeRunnable([ValueError(f"fail {i}") for i in range(L.MAX_RETRIES)])
    _patch_structured(monkeypatch, r)
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", True)
    with pytest.raises(ValueError, match="fail"):
        L.structured_invoke(Out, "p")
    assert r.calls == L.MAX_RETRIES


def test_a_parsing_error_counts_as_a_failed_attempt(monkeypatch):
    r = FakeRunnable([{"raw": None, "parsed": None, "parsing_error": "schema mismatch"},
                      {"raw": None, "parsed": Out(value="fixed"), "parsing_error": None}])
    _patch_structured(monkeypatch, r)
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", True)
    assert L.structured_invoke(Out, "p").value == "fixed" and r.calls == 2


def test_include_raw_is_requested_only_for_providers_that_support_it(monkeypatch):
    """NVIDIA's with_structured_output() raises NotImplementedError for include_raw=True,
    which broke all project generation in production."""
    ok = {"raw": None, "parsed": Out(value="v"), "parsing_error": None}

    seen = {}
    _patch_structured(monkeypatch, FakeRunnable([ok]), seen)
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", True)
    L.structured_invoke(Out, "p")
    assert seen.get("include_raw") is True

    seen.clear()
    _patch_structured(monkeypatch, FakeRunnable([Out(value="v")]), seen)
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", False)
    assert L.structured_invoke(Out, "p").value == "v"
    assert "include_raw" not in seen


def test_token_usage_from_the_raw_message_is_recorded(monkeypatch):
    class Raw:
        usage_metadata = {"input_tokens": 11, "output_tokens": 5}

    run = O.start_run("s")
    _patch_structured(monkeypatch, FakeRunnable([{"raw": Raw(), "parsed": Out(value="v"), "parsing_error": None}]))
    monkeypatch.setattr(L, "SUPPORTS_INCLUDE_RAW", True)
    L.structured_invoke(Out, "p", agent="planner")
    snap = run.snapshot()
    assert snap["input_tokens"] == 11 and snap["output_tokens"] == 5 and snap["per_agent"]["planner"]["calls"] == 1


def test_simple_invoke_returns_text_and_records_usage(monkeypatch):
    class Msg:
        content = "pong"
        usage_metadata = {"input_tokens": 3, "output_tokens": 1}

    run = O.start_run("s")
    monkeypatch.setattr(L, "llm", FakeLLM(invoke=lambda prompt, config: Msg()))
    assert L.simple_invoke("ping", agent="explainer") == "pong"
    assert run.snapshot()["total_tokens"] == 4


# ----------------------------------------------------------------------- truncation

def test_truncation_fallback_is_character_based_and_marked(monkeypatch):
    monkeypatch.setattr(L, "_get_tokenizer", lambda: None)   # e.g. Hugging Face unreachable
    out = L.truncate_for_context("x" * 500, max_chars=100)
    assert out == "x" * 100 + L._TRUNCATION_SUFFIX


def test_short_text_is_never_truncated(monkeypatch):
    monkeypatch.setattr(L, "_get_tokenizer", lambda: None)
    assert L.truncate_for_context("short", max_chars=100) == "short"


def test_token_budget_truncation_uses_the_tokenizer(monkeypatch):
    class Enc:
        def __init__(self, ids):
            self.ids = ids

    class FakeTok:   # 1 token per character
        def encode(self, text):
            return Enc(list(text))

        def decode(self, ids):
            return "".join(ids)

    monkeypatch.setattr(L, "_get_tokenizer", lambda: FakeTok())
    out = L.truncate_for_context("abcdefgh" * 10, max_chars=40)      # 40 // 4 = 10 tokens
    assert out == "abcdefghab" + L._TRUNCATION_SUFFIX


# --------------------------------------------------------------------- trace configs

def test_trace_config_tags_provider_agent_and_session():
    cfg = L._trace_config("planner", "planner", "sess-1")
    assert cfg["run_name"] == "planner"
    assert cfg["tags"] == [L.LLM_PROVIDER, "planner"]
    assert cfg["metadata"]["session_id"] == "sess-1" and cfg["metadata"]["model"] == L.MODEL_NAME
    assert "callbacks" not in cfg            # Langfuse is off in tests


def test_graph_run_config_names_tags_and_groups_the_whole_run():
    """Without this the LangSmith root run was untagged and Langfuse filed every
    node as its own session-less root trace."""
    cfg = L.graph_run_config("editing", "sess-7", 42)
    assert cfg["recursion_limit"] == 42
    assert cfg["run_name"] == "editing_run"
    assert cfg["tags"] == [L.LLM_PROVIDER, "editing"]
    assert cfg["metadata"]["session_id"] == "sess-7"


def test_graph_run_config_without_a_session_still_works():
    cfg = L.graph_run_config("qa", None, 10)
    assert "session_id" not in cfg["metadata"]


def test_background_tasks_pass_the_graph_config_to_every_graph():
    import inspect
    from backend import background_tasks as BT

    src = inspect.getsource(BT)
    for mode in ("generation", "editing", "qa"):
        assert f'graph_run_config("{mode}", session_id, recursion_limit)' in src
    assert '{"recursion_limit": recursion_limit}' not in src
