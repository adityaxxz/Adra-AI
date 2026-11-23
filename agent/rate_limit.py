"""Reading provider rate-limit errors (Groq, Gemini, ...).

Dependency-free on purpose: `agent.llm_client` builds the production model at import time and needs
API keys, while the eval judge only needs to read an error message.
"""
import re

_RETRY_IN = re.compile(r"(?:try again|retry) in ((?:[\d.]+(?:ms|h|m|s))+)", re.I)     # "try again in 3.98s", "retry in 20h14m46.7s"
_RETRY_DELAY = re.compile(r"retryDelay'?\"?:\s*'?\"?([\d.]+)s", re.I)                  # Gemini's structured form: 'retryDelay': '72886s'
_MARKERS = ("429", "rate limit", "rate_limit", "resource exhausted", "resource_exhausted", "too many requests", "quota")
_UNITS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
DAILY_AFTER_SECONDS = 90         # a limit that asks for longer than this won't clear within a request or an eval run


def _seconds(text: str) -> float:
    return sum(float(n) * _UNITS[u] for n, u in re.findall(r"([\d.]+)(ms|h|m|s)", text))


def classify_rate_limit(error: BaseException) -> tuple[str, float]:
    """('daily'|'rate'|'other', seconds the provider asked us to wait; 0 if it didn't say).

    'daily' is a quota that cannot clear soon (per-day caps, or a delay of many minutes), so waiting is
    pointless; 'rate' is a per-minute style limit that clears if we wait the hinted time."""
    text = str(error)
    low = text.lower()
    if not any(m in low for m in _MARKERS):
        return "other", 0.0
    m, d = _RETRY_IN.search(text), _RETRY_DELAY.search(text)
    wait = _seconds(m.group(1)) if m else (float(d.group(1)) if d else 0.0)
    if "per day" in low or "perday" in low or wait > DAILY_AFTER_SECONDS:
        return "daily", wait
    return "rate", wait
