from concurrent.futures import ThreadPoolExecutor

import pytest
from prometheus_client import REGISTRY

from agent import observability as O


@pytest.fixture(autouse=True)
def _clean_run():
    yield
    O.current_run.set(None)


def test_record_call_accumulates_tokens_cost_latency_and_per_agent_buckets():
    run = O.start_run("sess-1")
    O.PRICES["unit-test-model"] = {"in": 1.0, "out": 2.0}  # $/1M tokens
    try:
        O.record_call("unit-test-model", "groq", {"input_tokens": 1_000_000, "output_tokens": 500_000}, 120.0, agent="planner")
        O.record_call("unit-test-model", "groq", {"input_tokens": 0, "output_tokens": 1_000_000}, 80.0, agent="coder")
    finally:
        del O.PRICES["unit-test-model"]

    snap = run.snapshot()
    assert snap["llm_calls"] == 2
    assert snap["input_tokens"] == 1_000_000 and snap["output_tokens"] == 1_500_000
    assert snap["total_tokens"] == 2_500_000
    assert snap["cost_usd"] == pytest.approx(1.0 + 1.0 + 2.0)      # 1M in + 0.5M out, then 1M out
    assert snap["latency_ms"] == pytest.approx(200.0)
    assert snap["per_agent"]["planner"]["calls"] == 1
    assert snap["per_agent"]["coder"]["output_tokens"] == 1_000_000


def test_unknown_model_costs_zero_instead_of_failing():
    run = O.start_run("s")
    O.record_call("model-nobody-priced", "groq", {"input_tokens": 100, "output_tokens": 100}, 1.0, agent="x")
    assert run.snapshot()["cost_usd"] == 0 and run.snapshot()["total_tokens"] == 200


def test_missing_usage_metadata_is_tolerated():
    # e.g. NVIDIA structured calls expose no usage_metadata
    run = O.start_run("s")
    O.record_call("openai/gpt-oss-120b", "nvidia", None, 5.0, agent="planner")
    assert run.snapshot()["llm_calls"] == 1 and run.snapshot()["total_tokens"] == 0


def test_no_active_run_is_a_safe_noop_for_the_run_totals():
    O.current_run.set(None)
    O.record_call("openai/gpt-oss-120b", "groq", {"input_tokens": 1, "output_tokens": 1}, 1.0, agent="a")
    O.record_retry("a")  # must not raise


def test_retries_are_counted():
    run = O.start_run("s")
    O.record_retry("coder")
    O.record_retry("coder")
    assert run.snapshot()["retries"] == 2


def test_concurrent_runs_on_different_threads_do_not_share_counters():
    """The reason RunMetrics lives in a ContextVar: the executor runs several agent runs at once."""
    def one_run(n):
        run = O.start_run(f"s{n}")
        for _ in range(n):
            O.record_call("openai/gpt-oss-120b", "groq", {"input_tokens": 1, "output_tokens": 1}, 1.0, agent="a")
        return run.snapshot()["llm_calls"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(one_run, [1, 2, 3, 4])) == [1, 2, 3, 4]


def test_prometheus_counters_mirror_each_call():
    labels = {"provider": "unit-prov", "agent": "unit-agent"}
    before = REGISTRY.get_sample_value("adra_llm_calls_total", labels) or 0
    tokens_before = REGISTRY.get_sample_value("adra_llm_tokens_total", {"provider": "unit-prov", "direction": "input"}) or 0
    O.start_run("s")
    O.record_call("openai/gpt-oss-120b", "unit-prov", {"input_tokens": 7, "output_tokens": 3}, 10.0, agent="unit-agent")
    assert REGISTRY.get_sample_value("adra_llm_calls_total", labels) == before + 1
    assert REGISTRY.get_sample_value("adra_llm_tokens_total", {"provider": "unit-prov", "direction": "input"}) == tokens_before + 7


def test_agent_run_outcomes_are_counted():
    labels = {"mode": "unit", "status": "success"}
    before = REGISTRY.get_sample_value("adra_agent_run_total", labels) or 0
    O.record_agent_run("unit", "success")
    assert REGISTRY.get_sample_value("adra_agent_run_total", labels) == before + 1


def test_langfuse_is_disabled_without_keys_and_hooks_are_noops():
    assert O.LANGFUSE_ENABLED is False
    assert O.get_langfuse_handler() is None
    fn = lambda: 42  # noqa: E731
    assert O.langfuse_observe("x")(fn) is fn
