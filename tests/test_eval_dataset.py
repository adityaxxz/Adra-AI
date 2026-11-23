"""The golden dataset is code: a wrong case silently corrupts every score derived from it.

These tests need no LLM, no network and no database. They prove each case is well-formed,
satisfiable, and capable of failing.
"""
from collections import Counter

import pytest

from evals import dataset as D
from evals.evaluators import evaluate as E
from evals.evaluators import structural as S

CASES = D.load_cases()
BY_ID = {c["id"]: c for c in CASES}
EDITING = [c for c in CASES if c["mode"] == "editing"]
QA = [c for c in CASES if c["mode"] == "question_answering"]
WITH_SOLUTION = [c for c in CASES if c.get("solution")]


def _required_failures(outcomes):
    return [o for o in outcomes if o.required and o.passed is False]


def _project(case):
    """The project a case's solution produces."""
    if case["mode"] == "editing":
        return {**D.fixture_files(case["fixture"]), **case["solution"]}
    return dict(case["solution"])


# ------------------------------------------------------------------ shape

def test_dataset_is_non_trivial_and_covers_every_mode_and_provenance():
    modes = Counter(c["mode"] for c in CASES)
    assert all(modes[m] >= 5 for m in D.MODES), modes
    assert len(CASES) >= 15
    sources = Counter(c["source"] for c in CASES)
    assert sources["hand-written"] and sources["seeded-verbatim"] and sources["seeded-inferred"], sources


def test_case_ids_are_unique_and_prefixed_by_mode():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), [i for i, n in Counter(ids).items() if n > 1]
    prefix = {"generation": "gen-", "editing": "edit-", "question_answering": "qa-"}
    assert all(c["id"].startswith(prefix[c["mode"]]) for c in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_is_well_formed(case):
    assert D.problems(case) == []


def test_unanswerable_and_hallucination_probes_exist():
    assert sum(1 for c in QA if c["expect"].get("unanswerable")) >= 1


# --------------------------------------------------------------- fixtures

@pytest.mark.parametrize("name", sorted(p.name for p in D.FIXTURES.iterdir() if p.is_dir()))
def test_fixture_repository_is_itself_healthy(name):
    files = D.fixture_files(name)
    assert files, name
    for fn in E.DEFAULT_CHECKS.values():
        o = fn(files)
        assert o.passed is not False, f"fixture {name}: {o.name}: {o.detail}"


# --------------------------------------------------- cases can fail, and can pass

@pytest.mark.parametrize("case", EDITING, ids=lambda c: c["id"])
def test_doing_nothing_never_passes_an_editing_case(case):
    """If the untouched repository passes, the case can't detect a no-op."""
    fixture = D.fixture_files(case["fixture"])
    outcomes = E.evaluate_project(case, after=fixture, before=fixture, run_exec=True)
    assert _required_failures(outcomes), f"{case['id']} passes on the untouched fixture"


@pytest.mark.parametrize("case", WITH_SOLUTION, ids=lambda c: c["id"])
def test_the_reference_solution_passes_every_required_check(case):
    """Proves the expectations (and the executable checks) are satisfiable and consistent."""
    before = D.fixture_files(case["fixture"]) if case["mode"] == "editing" else None
    outcomes = E.evaluate_project(case, after=_project(case), before=before, run_exec=True)
    assert not _required_failures(outcomes), [(o.name, o.detail) for o in _required_failures(outcomes)]
    if case["expect"].get("exec"):
        executed = [o for o in outcomes if o.kind == "exec"]
        assert executed and all(o.passed for o in executed), [(o.name, o.detail) for o in executed]


def test_every_case_with_executable_checks_has_a_solution_proving_them():
    # an exec check nobody has ever seen pass is a liability
    missing = [c["id"] for c in CASES if c["expect"].get("exec") and not c.get("solution")]
    assert missing == []


# -------------------------------------------------------------- editing expectations

@pytest.mark.parametrize("case", EDITING, ids=lambda c: c["id"])
def test_editing_expectations_refer_to_real_files_and_symbols(case):
    fixture = D.fixture_files(case["fixture"])
    exp = case["expect"]
    for pat in exp.get("unmodified", []):
        assert S._match(fixture, pat), f"unmodified {pat!r} matches nothing in the fixture"
    for rule in exp.get("preserved_symbols", []):
        have = S._defs(rule["file"], fixture.get(rule["file"], ""))
        assert set(rule["names"]) <= have, f"{rule['file']} lacks {set(rule['names']) - have} before the edit"
    for pat in exp.get("modified", []):
        assert S._match(fixture, pat), f"modified {pat!r} matches nothing in the fixture"


# ------------------------------------------------------------------------- Q&A

@pytest.mark.parametrize("case", QA, ids=lambda c: c["id"])
def test_qa_sources_exist_in_the_fixture(case):
    fixture = D.fixture_files(case["fixture"])
    for src in case["expect"]["sources"]:
        assert src in fixture, f"{src} is not in fixture {case['fixture']}"


@pytest.mark.parametrize("case", QA, ids=lambda c: c["id"])
def test_the_reference_answer_satisfies_its_own_deterministic_checks(case):
    outcomes = E.evaluate_answer(case, case["reference"], retrieved_paths=case["expect"]["sources"])
    assert not _required_failures(outcomes), [(o.name, o.detail) for o in _required_failures(outcomes)]


@pytest.mark.parametrize("case", [c for c in QA if c["expect"].get("answer_contains")], ids=lambda c: c["id"])
def test_a_confident_wrong_answer_fails_the_deterministic_checks(case):
    """The checks must be able to reject something: an answer that says nothing relevant."""
    outcomes = E.evaluate_answer(case, "The weather is lovely today.", retrieved_paths=case["expect"]["sources"])
    assert _required_failures(outcomes)


def test_unanswerable_cases_reject_an_invented_mechanism():
    for case in (c for c in QA if c["expect"].get("unanswerable")):
        invented = "It authenticates users with JWT bearer tokens issued by an OAuth2 provider."
        assert _required_failures(E.evaluate_answer(case, invented, case["expect"]["sources"])), case["id"]


def test_qa_05_rejects_the_hedged_wrong_answer_the_agent_actually_gave():
    """Live 2026-11-23: the agent never saw storage.py, guessed 'an empty list with 200 OK', and hedged with
    'if the storage layer raised an error when the file is missing'. A bare 'error'/'missing' keyword check passed it."""
    from evals.evaluators import structural as S
    case = next(c for c in CASES if c["id"] == "qa-05-todo-get-before-create")
    wrong = ("In the typical implementation of storage.load_todos() (not shown here) it returns an empty list, so the endpoint "
             "responds 200 OK with []. If the storage layer were to raise an error when the file is missing, that would be "
             "the only deviation.")
    assert S.answer_contains(wrong, case["expect"]["answer_contains"]).passed is False
    assert S.answer_contains(case["reference"], case["expect"]["answer_contains"]).passed
    assert S.answer_contains("It raises FileNotFoundError, so the request fails with a 500.", case["expect"]["answer_contains"]).passed
