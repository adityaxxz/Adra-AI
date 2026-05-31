import os
import time
import threading
from typing import Type, TypeVar
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

load_dotenv()

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


#! MODELS
# llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)


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
            if _is_rate_limit_error(e) and attempt < MAX_RETRIES - 1:
                continue
            raise

    raise last_error or RuntimeError("Structured invoke failed after retries")
