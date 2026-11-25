"""Keep eval traffic off the key the app uses.

Groq's on-demand tier allows 200,000 tokens a day per account (a full eval run is ~92k), so evals that share the app's
key starve it (and vice versa). If GROQ_API_KEY_TEST is set, the evals' agents use it instead of GROQ_API_KEY; the app
itself never reads GROQ_API_KEY_TEST.
"""
import os
from typing import MutableMapping, Optional


def use_test_key(env: Optional[MutableMapping] = None) -> bool:
    """Point GROQ_API_KEY at GROQ_API_KEY_TEST for this process. Must run before `agent.llm_client` is imported, which
    builds the model from the environment. Returns whether the test key was applied."""
    env = os.environ if env is None else env
    test_key = (env.get("GROQ_API_KEY_TEST") or "").strip()
    if not test_key:
        return False
    env["GROQ_API_KEY"] = test_key
    return True
