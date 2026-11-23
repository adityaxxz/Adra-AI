"""Reading real provider rate-limit messages."""
import pytest

from agent.rate_limit import classify_rate_limit

GROQ = "Error code: 429 - {'error': {'message': 'Rate limit reached ... on tokens per minute (TPM). Please try again in 3.9825s.'}}"


@pytest.mark.parametrize("message, kind, wait", [
    (GROQ, "rate", 3.9825),
    ("429 RESOURCE_EXHAUSTED per minute. Please retry in 35.2s.", "rate", 35.2),
    ("429 Rate limit reached. Please try again in 250ms.", "rate", 0.25),
    ("429 Rate limit reached on tokens per day. Please try again in 17m30s.", "daily", 1050.0),
    ("429 Quota exceeded ... requests per day limit exceeded. Please retry in 20h14m46.5s.", "daily", 72886.5),
    ("429 RESOURCE_EXHAUSTED {'details': [{'retryDelay': '72886s'}]}", "daily", 72886.0),
    ("429 Too Many Requests", "rate", 0.0),
    ("503 backend unavailable", "other", 0.0),
])
def test_classifies_real_messages(message, kind, wait):
    k, w = classify_rate_limit(RuntimeError(message))
    assert k == kind and w == pytest.approx(wait)
