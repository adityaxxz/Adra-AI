"""Reading provider rate-limit errors (Groq, Gemini, ...).

Dependency-free on purpose: `agent.llm_client` builds the production model at import time and needs
API keys, while the eval judge only needs to read an error message.
"""
import logging
import re
import time
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")

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


def rate_limit_wait(error: BaseException, retry_number: int, max_wait: float) -> Optional[float]:
    """Seconds to wait before retrying after a rate limit, or None when waiting can't help: not a rate limit,
    a quota that won't clear soon (per-day), or a provider hint longer than `max_wait`."""
    kind, hint = classify_rate_limit(error)
    if kind != "rate" or hint > max_wait:
        return None
    # Providers say when the window frees up ("try again in 3.98s"); without a hint back off 5s, 10s, 20s...
    return hint + 1.0 if hint else min(5.0 * 2 ** retry_number, max_wait)


def call_with_rate_limit_backoff(call: Callable[[], T], *, retries: int, max_wait: float, label: str = "llm") -> T:
    """Run `call()`; on a rate limit wait the provider's suggested time and run it again, up to `retries` times.
    Anything else, and rate limits that waiting can't fix, are raised immediately."""
    attempt = 0
    while True:
        try:
            return call()
        except Exception as e:
            wait = rate_limit_wait(e, attempt, max_wait) if attempt < retries else None
            if wait is None:
                raise
            attempt += 1
            logger.warning(f"{label}: rate limit hit; waiting {wait:.1f}s before retry {attempt}/{retries}: {str(e)[:160]}")
            time.sleep(wait)
