"""App-level tests that need no database: lifespan is not run (TestClient used
without a context manager) and conftest points every datastore at nothing."""
from fastapi.testclient import TestClient

import backend.main as M

client = TestClient(M.app)


def test_sqlalchemy_echo_is_off():
    # echo=True logged every statement twice, with bound parameters (user code and answers)
    assert M.engine.echo is False


def test_health_is_503_and_names_each_failing_dependency():
    r = client.get("/health")
    assert r.status_code == 503, "a static 200 is a false green"
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"].startswith("error")
    assert body["checks"]["vector_store"].startswith("error")


def test_metrics_endpoint_serves_http_and_adra_metric_families():
    client.get("/health")     # generate one request for the instrumentator to count
    r = client.get("/metrics")
    assert r.status_code == 200
    for family in ("adra_llm_calls_total", "adra_llm_tokens_total", "adra_llm_cost_usd_total",
                   "adra_llm_call_latency_seconds", "adra_agent_run_total"):
        assert family in r.text
    assert "http_request" in r.text


def test_protected_endpoints_reject_anonymous_requests():
    assert client.get("/repositories").status_code in (401, 403)
    assert client.post("/generate", json={"prompt": "x"}).status_code in (401, 403)
    assert client.post("/repositories/abc/index?session_id=s").status_code in (401, 403)


def test_generate_and_index_endpoints_take_background_tasks():
    """They must return before the agent run finishes (Heroku kills requests at 30s)."""
    import inspect
    from fastapi import BackgroundTasks

    for fn in (M.start_generation, M.index_repository_endpoint):
        assert any(p.annotation is BackgroundTasks for p in inspect.signature(fn).parameters.values()), fn.__name__
