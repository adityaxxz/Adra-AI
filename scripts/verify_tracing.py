"""
verify_tracing.py — Quick smoke-test for Langfuse and LangSmith API keys.

Run from project root:
    uv run python scripts/verify_tracing.py

Loads keys from .env.prod (mimics the production config).
"""
import io, os, sys, time, uuid

# Force UTF-8 output on Windows so we don't get cp1252 encode errors
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Load prod env ─────────────────────────────────────────────────────────────
from dotenv import dotenv_values

PROD_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env.prod")
prod_vars = dotenv_values(PROD_ENV_PATH)

# Inject into os.environ so SDK clients pick them up
for k, v in prod_vars.items():
    if v is not None:
        # Strip surrounding quotes that some .env parsers leave in
        os.environ[k] = v.strip('"').strip("'")

# ── Helpers ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}[PASS]{RESET}  {msg}")
def fail(msg): print(f"  {RED}[FAIL]{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}[WARN]{RESET}  {msg}")
def section(title): print(f"\n{BOLD}{title}{RESET}")

results = {}

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  LANGFUSE
# ═══════════════════════════════════════════════════════════════════════════════
section("1. Langfuse")

LF_PK  = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LF_SK  = os.getenv("LANGFUSE_SECRET_KEY", "")
LF_URL = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

print(f"  Public key : {LF_PK[:12]}...")
print(f"  Secret key : {LF_SK[:12]}...")
print(f"  Base URL   : {LF_URL}")

if not LF_PK or not LF_SK:
    fail("Missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY -- skipping")
    results["langfuse"] = False
else:
    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=LF_PK,
            secret_key=LF_SK,
            host=LF_URL,
        )

        # auth_check() returns True/False and raises on network error
        auth_ok = lf.auth_check()
        if not auth_ok:
            raise RuntimeError("auth_check() returned False -- invalid credentials")

        ok("Auth check passed")

        # Send a test span (top-level, tied to its own trace)
        trace_id = lf.create_trace_id()
        span = lf.start_observation(
            trace_context={"trace_id": trace_id},
            name="adra-ai-verify-tracing",
            as_type="span",
            input={"test": True},
        )

        # Nest a child span using the span's own start_observation helper
        child = span.start_observation(
            name="smoke-test-span",
            as_type="span",
            input={"check": "api-key"},
        )
        child.update(output={"result": "ok"})
        child.end()
        span.update(output={"status": "ok"})
        span.end()

        # flush() sends buffered events; raises on auth or network failure
        lf.flush()

        ok(f"Trace sent successfully! (trace_id={trace_id})")
        ok(f"View at: {LF_URL}/trace/{trace_id}")
        results["langfuse"] = True

    except Exception as e:
        fail(f"Langfuse test FAILED: {e}")
        results["langfuse"] = False


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  LANGSMITH
# ═══════════════════════════════════════════════════════════════════════════════
section("2. LangSmith")

LS_KEY      = os.getenv("LANGSMITH_API_KEY", "")
LS_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
LS_PROJECT  = os.getenv("LANGSMITH_PROJECT", "default")

print(f"  API key    : {LS_KEY[:18]}...")
print(f"  Endpoint   : {LS_ENDPOINT}")
print(f"  Project    : {LS_PROJECT}")

if not LS_KEY:
    fail("Missing LANGSMITH_API_KEY -- skipping")
    results["langsmith"] = False
else:
    try:
        from langsmith import Client

        client = Client(api_url=LS_ENDPOINT, api_key=LS_KEY)

        # Check auth by listing projects (cheap read call)
        projects = list(client.list_projects())
        project_names = [p.name for p in projects]

        if project_names:
            ok(f"Auth OK -- found {len(project_names)} project(s): {project_names[:5]}")
        else:
            warn("Auth OK but no projects found yet (might be a brand-new key)")

        # Try creating a test run in the target project
        from datetime import datetime, timezone
        run_id = str(uuid.uuid4())
        client.create_run(
            project_name=LS_PROJECT,
            id=run_id,
            name="adra-ai-verify-tracing",
            run_type="chain",
            inputs={"test": True},
            start_time=datetime.now(timezone.utc),
        )
        client.update_run(
            run_id=run_id,
            outputs={"status": "ok"},
            end_time=datetime.now(timezone.utc),
        )

        ok(f"Test run created in project '{LS_PROJECT}' (run_id={run_id})")
        ok(f"View at: https://smith.langchain.com/projects/{LS_PROJECT}/runs/{run_id}")
        results["langsmith"] = True

    except Exception as e:
        fail(f"LangSmith test FAILED: {e}")
        results["langsmith"] = False

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
section("Summary")
for svc, passed in results.items():
    if passed:
        ok(f"{svc:12s} -> PASS")
    else:
        fail(f"{svc:12s} -> FAIL")

if not all(results.values()):
    print(f"\n{RED}One or more tracing services failed. Fix keys before deploying.{RESET}")
    sys.exit(1)
else:
    print(f"\n{GREEN}All tracing services verified -- safe to push to Heroku.{RESET}")
    sys.exit(0)
