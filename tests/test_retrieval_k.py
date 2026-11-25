"""How many chunks the agents retrieve, and that the eval harness measures that same number."""
import inspect

from agent import graph as G
from agent.repository import retriever as RT
from agent.repository import service as S
from agent.repository.models import DEFAULT_RETRIEVAL_K
from evals import runner as R


def test_the_agents_retrieve_eight_chunks_not_five():
    """Five missed an expected file for 5 of 14 questions on a realistic repo (recall 0.70); eight reached 0.94."""
    assert DEFAULT_RETRIEVAL_K == 8


def test_the_search_functions_default_to_the_shared_constant():
    assert inspect.signature(S.search_repository).parameters["k"].default == DEFAULT_RETRIEVAL_K
    assert inspect.signature(RT.retrieve).parameters["k"].default == DEFAULT_RETRIEVAL_K


def test_the_repository_agent_does_not_override_k(monkeypatch):
    seen = {}
    monkeypatch.setattr(G, "search_repository", lambda query, **kw: seen.update(kw) or [])
    G.repository_agent({"user_prompt": "q", "collection_name": "c"})
    assert "k" not in seen, "the agent must use the default, or the constant stops describing the pipeline"


def test_the_eval_harness_measures_the_agents_own_k():
    """QA_K used to be a separate constant (5): changing the agent's k would have left the retrieval metrics
    describing a pipeline that no longer existed."""
    assert R.QA_K == DEFAULT_RETRIEVAL_K


def test_the_retrieval_metric_looks_at_every_chunk_the_agent_retrieved_not_just_the_first_five():
    """evaluate_answer had its own `k = 5`: with the agent retrieving 8, a source file ranked 6th-8th was reported as
    missed (and 'saw' listed only the top 5), although the judge was shown all 8 chunks."""
    from evals.evaluators import evaluate as E

    case = {"mode": "question_answering", "prompt": "q", "expect": {"sources": ["storage.py"]}}
    retrieved = ["README.md"] * 5 + ["main.py", "storage.py", "main.py"][:DEFAULT_RETRIEVAL_K - 5]
    assert len(retrieved) == DEFAULT_RETRIEVAL_K and retrieved.index("storage.py") >= 5
    detail = next(o for o in E.evaluate_answer(case, "some answer", retrieved) if o.name == "retrieval")
    assert detail.passed is True and "storage.py" in detail.detail and f"hit@{DEFAULT_RETRIEVAL_K}" in detail.detail
