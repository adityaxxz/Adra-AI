import logging
import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
load_dotenv()

from agent.rate_limit import call_with_rate_limit_backoff

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


embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001",)

# Indexing embeds one chunk per call, so a repo of ~100+ chunks exceeds the free tier's 100 calls/minute.
EMBED_RATE_LIMIT_RETRIES = int(os.getenv("EMBED_RATE_LIMIT_RETRIES", "5"))
EMBED_RATE_LIMIT_MAX_WAIT_SEC = float(os.getenv("EMBED_RATE_LIMIT_MAX_WAIT_SEC", "60"))


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("429", "rate limit", "resource exhausted", "too many requests")
    )


def embed_text(text: str, *, task_type: str) -> list[float]:
    """Embed text with an explicit Gemini `task_type`.

    Gemini's embedding model computes different (asymmetric) vectors depending
    on whether the text is a document being indexed or a query being searched
    with: use `"RETRIEVAL_DOCUMENT"` for chunk content at index time and
    `"RETRIEVAL_QUERY"` for search queries. Mixing them up produces poorly
    calibrated similarity scores. `task_type` is required (no default) so
    every call site has to make this choice explicitly.
    """
    try:
        return call_with_rate_limit_backoff(
            lambda: embeddings.embed_query(text, task_type=task_type),
            retries=EMBED_RATE_LIMIT_RETRIES, max_wait=EMBED_RATE_LIMIT_MAX_WAIT_SEC, label="embeddings",
        )
    except Exception as e:
        if _is_rate_limit_error(e):
            logger.error(f"Google GenAI Embeddings Rate Limit / Resource Exhausted (429) hit: {e}")
            raise
        raise