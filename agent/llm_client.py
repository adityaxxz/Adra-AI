import os
import time
import logging
import threading
from typing import Optional, Type, TypeVar
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

from agent.observability import record_call, record_retry, get_current_run, get_langfuse_handler

logger = logging.getLogger(__name__)


def patch_google_genai_retries():
    try:
        import google.genai.client
        from google.genai import types
        
        # Avoid patching multiple times
        if getattr(google.genai.client.Client, "_retries_patched", False):
            return
            
        original_init = google.genai.client.Client.__init__
        
        def new_init(self, *args, **kwargs):
            http_options = kwargs.get("http_options")
            if http_options is None:
                http_options = types.HttpOptions()
            
            if isinstance(http_options, dict):
                retry_options = http_options.get("retry_options")
                if retry_options is None:
                    http_options["retry_options"] = types.HttpRetryOptions(attempts=1)
                elif isinstance(retry_options, dict):
                    retry_options["attempts"] = 1
                else:
                    retry_options.attempts = 1
            else:
                if http_options.retry_options is None:
                    http_options.retry_options = types.HttpRetryOptions(attempts=1)
                elif isinstance(http_options.retry_options, dict):
                    http_options.retry_options["attempts"] = 1
                else:
                    http_options.retry_options.attempts = 1
                
            kwargs["http_options"] = http_options
            original_init(self, *args, **kwargs)
            
        google.genai.client.Client.__init__ = new_init
        google.genai.client.Client._retries_patched = True
    except Exception as e:
        logger.warning(f"Failed to patch google-genai client retries: {e}")

# Apply global patch to disable google-genai SDK internal retries
patch_google_genai_retries()


#################################### MODELS ################################

# Configure LLM provider based on environment variable
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

if LLM_PROVIDER == "nvidia":
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    if not nvidia_api_key:
        raise ValueError("NVIDIA_API_KEY environment variable is required when LM_PROVIDER=nvidia")

    MODEL_NAME = "nvidia/nemotron-3.5-lightning-30b-a3b"
    # Nemotron 3.5 Lightning 30B — NVIDIA's own model, active on NIM.
    # thinking/reasoning is intentionally OFF: this app uses json_schema structured
    # output (with_structured_output) which requires strict schema-compliant responses.
    # Enabling thinking causes ForgivingPydanticOutputParser to loop endlessly.
    llm = ChatNVIDIA(
        model=MODEL_NAME,
        api_key=nvidia_api_key,
        temperature=0,
        top_p=0.95,
        max_tokens=4096,
        timeout=120,
    )
elif LLM_PROVIDER == "groq":
    MODEL_NAME = "openai/gpt-oss-120b"
    llm = ChatGroq(model=MODEL_NAME, temperature=0)
elif LLM_PROVIDER == "gemini":
    MODEL_NAME = "gemini-2.5-flash"
    llm = ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=0, max_retries=0)
else:
    raise ValueError(f"Unknown LLM provider: {LLM_PROVIDER}. Supported providers: gemini, groq, nvidia")

# ChatNVIDIA.with_structured_output() unconditionally raises NotImplementedError
# for include_raw=True (see langchain_nvidia_ai_endpoints/chat_models.py), so it
# can't use the include_raw path structured_invoke() relies on to recover
# usage_metadata. Structured output still works for it, just without token/cost
# capture for that call.
SUPPORTS_INCLUDE_RAW = LLM_PROVIDER != "nvidia"



T = TypeVar("T", bound=BaseModel)

MIN_INTERVAL_SEC = float(os.getenv("LLM_MIN_INTERVAL_SEC", "2.1"))
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
MAX_CONTENT_CHARS = int(os.getenv("LLM_MAX_CONTENT_CHARS", "10000"))

lock = threading.Lock()
last_call_at = 0.0
call_count = 0


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("429", "rate limit", "resource exhausted", "too many requests", "quota exceeded")
    )


def _throttle(extra_wait: float = 0.0) -> None:
    global last_call_at, call_count
    with lock:
        now = time.monotonic()
        wait = MIN_INTERVAL_SEC - (now - last_call_at) + extra_wait
        if wait > 0:
            time.sleep(wait)
        last_call_at = time.monotonic()
        call_count += 1


_tokenizer = None
_tokenizer_load_failed = False
_TRUNCATION_SUFFIX = "\n\n... [truncated to stay within token limits] ..."


def _get_tokenizer():
    """Lazily load a BPE tokenizer to budget truncation on real tokens instead
    of raw characters. Falls back to `None` (char-based truncation) if it
    can't be loaded, e.g. no network access to fetch the tokenizer file."""
    global _tokenizer, _tokenizer_load_failed
    if _tokenizer is not None or _tokenizer_load_failed:
        return _tokenizer
    try:
        from tokenizers import Tokenizer
        _tokenizer = Tokenizer.from_pretrained("gpt2")
    except Exception as e:
        _tokenizer_load_failed = True
        logger.warning(f"Falling back to char-based truncation, tokenizer load failed: {e}")
    return _tokenizer


def truncate_for_context(text: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Truncate text to stay within a token budget approximated from `max_chars`
    (~4 chars/token), so multi-byte/dense code isn't over- or under-truncated
    relative to a plain character cutoff."""
    tokenizer = _get_tokenizer()
    if tokenizer is None:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + _TRUNCATION_SUFFIX

    max_tokens = max(1, max_chars // 4)
    encoding = tokenizer.encode(text)
    if len(encoding.ids) <= max_tokens:
        return text
    return tokenizer.decode(encoding.ids[:max_tokens]) + _TRUNCATION_SUFFIX


def get_stats() -> dict:
    stats = {
        "api_calls": call_count,
        "min_interval_sec": MIN_INTERVAL_SEC,
        "provider": LLM_PROVIDER,
        "model": MODEL_NAME,
    }
    run = get_current_run()
    if run is not None:
        stats["current_run"] = run.snapshot()
    return stats




# Built once at import time, same as `llm` above. Only non-None once
# LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are set in the environment.
_langfuse_handler = get_langfuse_handler()


def _trace_config(run_name: str, agent: Optional[str], session_id: Optional[str]) -> dict:
    """Build a LangChain `config=` dict so runs show up in LangSmith (when
    LANGSMITH_TRACING_V2/LANGSMITH_TRACING is enabled) tagged by agent and
    correlated to a session, and — if configured — in Langfuse at the same
    time via an explicit callback. The two tracers are independent and don't
    conflict; both can be active simultaneously for side-by-side comparison."""
    tags = [LLM_PROVIDER]
    if agent:
        tags.append(agent)

    metadata = {"provider": LLM_PROVIDER, "model": MODEL_NAME}
    if session_id:
        metadata["session_id"] = session_id

    config = {"run_name": run_name, "tags": tags, "metadata": metadata}

    if _langfuse_handler is not None:
        config["callbacks"] = [_langfuse_handler]
        # Reserved Langfuse metadata keys that map to first-class trace fields
        # (https://langfuse.com/integrations/frameworks/langchain).
        metadata["langfuse_tags"] = tags
        if session_id:
            metadata["langfuse_session_id"] = session_id

    return config


def structured_invoke(
    schema: Type[T],
    prompt: str,
    *,
    agent: Optional[str] = None,
    session_id: Optional[str] = None,
) -> T:
    """One throttled LLM call with Groq-compatible json_schema output.

    `agent`/`session_id` tag the LangSmith trace and the token/cost/latency
    metrics recorded for this call (see `agent.observability`).
    """

    if SUPPORTS_INCLUDE_RAW:
        runnable = llm.with_structured_output(schema, method="json_schema", include_raw=True)
    else:
        runnable = llm.with_structured_output(schema, method="json_schema")
    config = _trace_config(agent or schema.__name__, agent, session_id)
    last_error: BaseException | None = None

    for attempt in range(MAX_RETRIES):
        _throttle(extra_wait=attempt * MIN_INTERVAL_SEC)

        try:
            start = time.monotonic()
            output = runnable.invoke(prompt, config=config)
            latency_ms = (time.monotonic() - start) * 1000

            raw = output.get("raw") if isinstance(output, dict) else None
            parsed = output.get("parsed") if isinstance(output, dict) else output
            parsing_error = output.get("parsing_error") if isinstance(output, dict) else None

            usage = getattr(raw, "usage_metadata", None) if raw is not None else None
            record_call(MODEL_NAME, LLM_PROVIDER, usage, latency_ms, agent=agent)

            if parsing_error is not None or parsed is None:
                raise ValueError(f"Structured output parsing failed for {schema.__name__}: {parsing_error}")
            return parsed

        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                logger.error(f"{LLM_PROVIDER.upper()} Rate Limit / Resource Exhausted (429) hit: {e}")
                raise
            record_retry(agent=agent)
            if attempt < MAX_RETRIES - 1:
                continue
            raise

    raise last_error or RuntimeError("Structured invoke failed after retries")


def simple_invoke(prompt: str, *, agent: Optional[str] = None, session_id: Optional[str] = None) -> str:
    """One throttled LLM call that returns plain text (no structured output)."""
    config = _trace_config(agent or "simple_invoke", agent, session_id)
    last_error: BaseException | None = None

    for attempt in range(MAX_RETRIES):
        _throttle(extra_wait=attempt * MIN_INTERVAL_SEC)

        try:
            start = time.monotonic()
            result = llm.invoke(prompt, config=config)
            latency_ms = (time.monotonic() - start) * 1000

            if result is None:
                raise ValueError("LLM returned None")

            usage = getattr(result, "usage_metadata", None)
            record_call(MODEL_NAME, LLM_PROVIDER, usage, latency_ms, agent=agent)
            return result.content

        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                logger.error(f"{LLM_PROVIDER.upper()} Rate Limit / Resource Exhausted (429) hit: {e}")
                raise
            record_retry(agent=agent)
            if attempt < MAX_RETRIES - 1:
                continue
            raise

    raise last_error or RuntimeError("Simple invoke failed after retries")
