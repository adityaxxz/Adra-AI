"""Centralized LLM run metrics: tokens, cost, latency, and retries.

Every call routed through `agent.llm_client.structured_invoke` / `simple_invoke`
reports here via `record_call`. Metrics are accumulated per-run (via a
contextvar, so concurrent agent runs on different threads don't clobber each
other) and mirrored into Prometheus counters/histograms for the `/metrics`
endpoint exposed by the backend.
"""
import contextvars
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
# Read env vars (LANGFUSE_*) directly at import time below — call load_dotenv()
# here too rather than relying on some other module having imported it first.
load_dotenv()

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram
    _PROM_ENABLED = True
except ImportError:  # pragma: no cover - prometheus_client is an optional/new dep
    _PROM_ENABLED = False

# Langfuse runs alongside LangSmith (not instead of it) so both can be
# compared during the trial period. It only activates once both keys are
# present in the environment — until then, every helper below is a no-op and
# `langfuse` itself is never imported, so there's zero cost/behavior change.
LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def get_langfuse_handler():
    """Build a Langfuse LangChain `CallbackHandler` if configured, else `None`.

    Safe to call unconditionally: callers should add the handler to a
    LangChain `config={"callbacks": [...]}` only when this returns non-None.
    """
    if not LANGFUSE_ENABLED:
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception as e:
        logger.warning(f"Langfuse callback handler could not be initialized, Langfuse tracing disabled: {e}")
        return None


def langfuse_observe(name: str, as_type: str = "span"):
    """Return Langfuse's `@observe` decorator if configured, else a no-op
    passthrough decorator. Lets `agent/graph.py` decorate every node
    unconditionally without importing `langfuse` (or touching its client) when
    it isn't configured."""
    if not LANGFUSE_ENABLED:
        return lambda func: func
    try:
        from langfuse import observe
        return observe(name=name, as_type=as_type)
    except Exception as e:
        logger.warning(f"Langfuse observe() unavailable, skipping: {e}")
        return lambda func: func

# Rough per-1M-token USD prices. Extend as new models/providers are added;
# unknown models simply record zero cost instead of failing.
PRICES: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"in": 0.075, "out": 0.30},
    "openai/gpt-oss-120b": {"in": 0.15, "out": 0.60},
    "meta/llama-3.1-8b-instruct": {"in": 0.05, "out": 0.05},
}

current_run: "contextvars.ContextVar[Optional[RunMetrics]]" = contextvars.ContextVar(
    "current_run", default=None
)

if _PROM_ENABLED:
    LLM_CALLS_TOTAL = Counter(
        "adra_llm_calls_total", "Total LLM invocations", ["provider", "agent"]
    )
    LLM_TOKENS_TOTAL = Counter(
        "adra_llm_tokens_total", "Total LLM tokens processed", ["provider", "direction"]
    )
    LLM_COST_USD_TOTAL = Counter(
        "adra_llm_cost_usd_total", "Total estimated LLM cost in USD", ["provider"]
    )
    LLM_CALL_LATENCY_SECONDS = Histogram(
        "adra_llm_call_latency_seconds", "LLM call latency in seconds", ["provider"]
    )
    AGENT_RUN_TOTAL = Counter(
        "adra_agent_run_total", "Total agent graph runs", ["mode", "status"]
    )


@dataclass
class RunMetrics:
    session_id: Optional[str] = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    retries: int = 0
    per_agent: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 1),
            "retries": self.retries,
            "per_agent": self.per_agent,
        }


def start_run(session_id: Optional[str] = None) -> RunMetrics:
    """Start a fresh RunMetrics for the current execution context.

    Call this at the top of each agent graph invocation (one per background
    task thread) so LLM calls made during that run roll up together.
    """
    run = RunMetrics(session_id=session_id)
    current_run.set(run)
    return run


def get_current_run() -> Optional[RunMetrics]:
    return current_run.get()


def record_retry(agent: Optional[str] = None) -> None:
    run = current_run.get()
    if run is not None:
        run.retries += 1


def record_call(
    model: str,
    provider: str,
    usage: Optional[dict],
    latency_ms: float,
    agent: Optional[str] = None,
) -> None:
    """Record one LLM call's token usage, cost, and latency."""
    usage = usage or {}
    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    prices = PRICES.get(model, {"in": 0.0, "out": 0.0})
    cost = (input_tokens * prices["in"] + output_tokens * prices["out"]) / 1_000_000

    run = current_run.get()
    if run is not None:
        run.llm_calls += 1
        run.input_tokens += input_tokens
        run.output_tokens += output_tokens
        run.cost_usd += cost
        run.latency_ms += latency_ms
        if agent:
            bucket = run.per_agent.setdefault(
                agent, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0.0}
            )
            bucket["calls"] += 1
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            bucket["latency_ms"] += latency_ms

    if _PROM_ENABLED:
        LLM_CALLS_TOTAL.labels(provider=provider, agent=agent or "unknown").inc()
        LLM_TOKENS_TOTAL.labels(provider=provider, direction="input").inc(input_tokens)
        LLM_TOKENS_TOTAL.labels(provider=provider, direction="output").inc(output_tokens)
        LLM_COST_USD_TOTAL.labels(provider=provider).inc(cost)
        LLM_CALL_LATENCY_SECONDS.labels(provider=provider).observe(latency_ms / 1000.0)

    logger.info(
        "llm_call",
        extra={
            "model": model,
            "provider": provider,
            "agent": agent,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "latency_ms": round(latency_ms, 1),
        },
    )


def record_agent_run(mode: str, status: str) -> None:
    """Record a completed agent graph run (project generation / editing / Q&A)."""
    if _PROM_ENABLED:
        AGENT_RUN_TOTAL.labels(mode=mode, status=status).inc()
