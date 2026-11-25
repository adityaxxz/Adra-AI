"""Keep eval traffic off the keys the app uses.

Free tiers have small daily limits per account/project (Groq: 200,000 tokens/day; a full eval run is ~92k), so evals that
share the app's keys starve it, and vice versa. Any `<NAME>_TEST` key set in the environment replaces `<NAME>` for the eval
process only; the app itself never reads the `_TEST` names.
"""
import os
from typing import MutableMapping, Optional

TEST_KEYS = {"GROQ_API_KEY_TEST": "GROQ_API_KEY", "GOOGLE_API_KEY_TEST": "GOOGLE_API_KEY"}


def use_test_keys(env: Optional[MutableMapping] = None) -> list[str]:
    """Point each real key at its `_TEST` counterpart when that is set (blank values are ignored). Must run before
    `agent.llm_client` / the embeddings module are imported: they build their clients from the environment.
    Returns the names of the test keys applied (names only, never values)."""
    env = os.environ if env is None else env
    applied = []
    for test_name, real_name in TEST_KEYS.items():
        value = (env.get(test_name) or "").strip()
        if value:
            env[real_name] = value
            applied.append(test_name)
    return applied
