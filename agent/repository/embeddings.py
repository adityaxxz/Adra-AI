import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
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


embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001",)


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("429", "rate limit", "resource exhausted", "too many requests")
    )


def embed_text(text: str) -> list[float]:
    try:
        return embeddings.embed_query(text)
    except Exception as e:
        if _is_rate_limit_error(e):
            print(f"\n[FATAL] Google GenAI Embeddings Rate Limit / Resource Exhausted (429) hit: {e}")
            print("Stopping the process immediately as requested.\n")
            import os
            os._exit(1)
        raise