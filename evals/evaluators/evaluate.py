"""Map a dataset case's `expect` block onto the evaluators."""
from typing import Optional

from evals.evaluators import structural as S
from evals.evaluators.outcome import Outcome, skipped
from evals.evaluators.retrieval import retrieval_outcome

# Always run (they are vacuous -> skipped when they don't apply). A case can opt out via expect.disable.
DEFAULT_CHECKS = {
    "python_parses": S.python_parses,
    "json_valid": S.json_valid,
    "js_parses": S.js_parses,
    "imports_resolve": S.imports_resolve,
    "html_refs_resolve": S.html_refs_resolve,
    "dom_ids_resolve": S.dom_ids_resolve,
    "no_placeholders": S.no_placeholders,
}

_PROJECT_KEYS = {"files_exist", "contains", "not_contains", "defines", "exec", "declared_dependencies", "disable"}
EXPECT_KEYS = {
    "generation": _PROJECT_KEYS,
    "editing": _PROJECT_KEYS | {"modified", "unmodified", "preserved_symbols", "allow_deleted"},
    "question_answering": {"sources", "answer_contains", "answer_not_contains", "unanswerable", "max_words", "k"},
}
JUDGE_KEYS = {"notes", "min_score", "skip"}


def evaluate_project(case: dict, after: dict, before: Optional[dict] = None, run_exec: bool = False) -> list[Outcome]:
    """Structural + executable checks for a generation or editing case."""
    expect = case.get("expect", {})
    disabled = set(expect.get("disable", []))
    out = [fn(after) for name, fn in DEFAULT_CHECKS.items() if name not in disabled]

    if "files_exist" in expect:
        out.append(S.files_exist(after, expect["files_exist"]))
    if "contains" in expect:
        out.append(S.contains(after, expect["contains"]))
    if "not_contains" in expect:
        out.append(S.not_contains(after, expect["not_contains"]))
    if "defines" in expect:
        out.append(S.defines(after, expect["defines"]))
    if expect.get("declared_dependencies"):
        out.append(S.declared_dependencies(after))

    if case["mode"] == "editing":
        before = before or {}
        out.append(S.no_files_deleted(before, after, expect.get("allow_deleted", [])))
        if "modified" in expect:
            out.append(S.modified(before, after, expect["modified"]))
        if "unmodified" in expect:
            out.append(S.unmodified(before, after, expect["unmodified"]))
        if "preserved_symbols" in expect:
            out.append(S.preserved_symbols(before, after, expect["preserved_symbols"]))

    if expect.get("exec"):
        if run_exec:
            out.extend(S.run_exec_checks(after, expect["exec"]))
        else:
            out.append(skipped("exec", "executable checks are off (pass --exec to run them)", kind="exec"))
    return out


def evaluate_answer(case: dict, answer: str, retrieved_paths: list[str]) -> list[Outcome]:
    """Deterministic checks for a question-answering case."""
    expect = case.get("expect", {})
    out = []
    if expect.get("sources"):
        out.append(retrieval_outcome(retrieved_paths, expect["sources"], expect.get("k", 5)))
    if not answer.strip():
        from evals.evaluators.outcome import fail
        return out + [fail("non_empty_answer", "the agent returned no answer")]
    if "answer_contains" in expect:
        out.append(S.answer_contains(answer, expect["answer_contains"]))
    if "answer_not_contains" in expect:
        out.append(S.answer_not_contains(answer, expect["answer_not_contains"]))
    if expect.get("unanswerable"):
        out.append(S.admits_unknown(answer))
    if "max_words" in expect:
        out.append(S.answer_max_words(answer, expect["max_words"]))
    return out
