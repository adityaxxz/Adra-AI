import os
import time
import threading
from typing import Type, TypeVar
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()


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
        print(f"Warning: Failed to patch google-genai client retries: {e}")

# Apply global patch to disable google-genai SDK internal retries
patch_google_genai_retries()


#################################### MODELS ################################

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, max_retries=0)
# llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)



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
        for token in ("429", "rate limit", "resource exhausted", "too many requests")
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


def truncate_for_context(text: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n... [truncated to stay within token limits] ..."


def get_stats() -> dict:
    return {"api_calls": call_count, "min_interval_sec": MIN_INTERVAL_SEC}




def structured_invoke(schema: Type[T], prompt: str) -> T:
    """One throttled LLM call with Groq-compatible json_schema output."""

    runnable = llm.with_structured_output(schema, method="json_schema")
    last_error: BaseException | None = None

    for attempt in range(MAX_RETRIES):
        _throttle(extra_wait=attempt * MIN_INTERVAL_SEC)

        try:
            result = runnable.invoke(prompt)
            if result is None:
                raise ValueError(f"Structured output returned None for {schema.__name__}")
            return result

        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                print(f"\n[ERROR] Google GenAI Rate Limit / Resource Exhausted (429) hit: {e}")
                raise
            if attempt < MAX_RETRIES - 1:
                continue
            raise

    raise last_error or RuntimeError("Structured invoke failed after retries")


def simple_invoke(prompt: str) -> str:
    """One throttled LLM call that returns plain text (no structured output)."""
    last_error: BaseException | None = None

    for attempt in range(MAX_RETRIES):
        _throttle(extra_wait=attempt * MIN_INTERVAL_SEC)

        try:
            result = llm.invoke(prompt)
            if result is None:
                raise ValueError("LLM returned None")
            return result.content

        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                print(f"\n[ERROR] Google GenAI Rate Limit / Resource Exhausted (429) hit: {e}")
                raise
            if attempt < MAX_RETRIES - 1:
                continue
            raise

    raise last_error or RuntimeError("Simple invoke failed after retries")
