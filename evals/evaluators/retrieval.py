"""Retrieval quality for Q&A: did the chunks the agent saw include the file(s) holding the answer?"""
from evals.evaluators.outcome import Outcome


def _norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def retrieval_metrics(retrieved: list[str], sources: list[str], k: int = 5) -> dict:
    """`retrieved` is the ranked file path of each retrieved chunk (duplicates allowed)."""
    top = [_norm(p) for p in retrieved[:k]]
    want = {_norm(s) for s in sources}
    ranks = [i + 1 for i, p in enumerate(top) if p in want]
    found = {p for p in top if p in want}
    return {
        "k": k,
        "hit": bool(ranks),                                       # any source file in the top k
        "recall": len(found) / len(want) if want else 1.0,        # share of the source files that surfaced
        "mrr": 1.0 / ranks[0] if ranks else 0.0,                  # 1 / rank of the first source chunk
        "precision": len([p for p in top if p in want]) / len(top) if top else 0.0,   # share of chunks from sources
    }


def retrieval_outcome(retrieved: list[str], sources: list[str], k: int = 5) -> Outcome:
    m = retrieval_metrics(retrieved, sources, k)
    detail = f"hit@{k}={m['hit']} recall={m['recall']:.2f} mrr={m['mrr']:.2f} precision={m['precision']:.2f}; saw {sorted({_norm(p) for p in retrieved[:k]})}"
    return Outcome("retrieval", "retrieval", m["hit"], detail, score=m["recall"], required=False)
