"""§2.4 "Regression gate in CI": the saved reference run and the pass/regression/inconclusive verdict."""
import json
from pathlib import Path

import pytest
import yaml

from evals import baseline as B
from evals import run_eval

ROOT = Path(__file__).resolve().parent.parent
IDS = [f"case-{i:02d}" for i in range(1, 16)]


def report(passing: int = 11, *, judge="gemini-2.5-flash-lite", exec_on=True, stopped=None, unjudged=0, complete=True,
           repeat=1, ids=IDS, fail_first=False):
    """A minimal report: `passing` of the cases pass (the first ones, or the last ones with fail_first)."""
    order = list(reversed(ids)) if fail_first else list(ids)
    passed = set(order[:passing])
    return {
        "meta": {"started": "2026-11-26T10:00:00", "git_sha": "abc12345def", "agent": {"provider": "groq"}, "judge": judge,
                 "exec": exec_on, "stopped_early": stopped, "complete": complete, "repeat": repeat},
        "summary": {"overall": {"judge_unavailable": unjudged}},
        "cases": [{"id": i, "status": "passed" if i in passed else "failed", "output_files": {"x.py": "big"}, "answer": "long"}
                  for i in ids],
    }


REF = B.to_baseline(report(11))


# ------------------------------------------------------------------ the saved reference

def test_the_reference_is_compact_and_records_how_it_was_measured():
    assert REF["passed"] == 11 and REF["total"] == 15 and len(REF["cases"]) == 15
    assert REF["judge"] == "gemini-2.5-flash-lite" and REF["exec"] is True and REF["git_sha"] == "abc12345def"
    assert "output_files" not in json.dumps(REF) and "long" not in json.dumps(REF), "no outputs or answers in the reference"


# ------------------------------------------------------------------ the verdict

@pytest.mark.parametrize("passing, verdict", [(11, B.PASS), (12, B.PASS), (10, B.PASS), (9, B.PASS), (8, B.REGRESSION), (3, B.REGRESSION)])
def test_more_than_two_fewer_passes_is_a_regression(passing, verdict):
    assert B.compare(report(passing), REF, max_drop=2)[0] == verdict


def test_the_explanation_names_the_cases_that_changed():
    verdict, lines = B.compare(report(11, fail_first=True), REF, max_drop=2)   # same count, different cases
    text = "\n".join(lines)
    assert verdict == B.PASS and "now failing: case-01" in text and "now passing:" in text


@pytest.mark.parametrize("kwargs, reason", [
    ({"stopped": "429 tokens per day"}, "stopped early"),
    ({"unjudged": 2}, "could not be judged"),
    ({"complete": False}, "did not finish"),
    ({"repeat": 2}, "--repeat 1"),
    ({"judge": "gemini-2.5-flash"}, "judged by"),
    ({"exec_on": False}, "executable checks"),
    ({"ids": IDS[:14]}, "different cases"),
])
def test_a_run_that_does_not_measure_the_same_thing_is_inconclusive_not_green(kwargs, reason):
    verdict, lines = B.compare(report(15, **kwargs), REF, max_drop=2)
    assert verdict == B.INCONCLUSIVE and reason in "\n".join(lines)


def test_exit_codes_distinguish_regression_from_cant_compare():
    assert (B.EXIT_CODES[B.PASS], B.EXIT_CODES[B.REGRESSION], B.EXIT_CODES[B.INCONCLUSIVE]) == (0, 1, 2)


# ------------------------------------------------------------------ the CLI

class _Pipe:
    """Answers every Q&A case with its reference, so all selected cases pass."""

    def __init__(self, *a, **k):
        from tests.test_eval_runner import FakePipeline
        self._p = FakePipeline()

    def __getattr__(self, name):
        return getattr(self._p, name)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    import dotenv
    import evals.pipeline as P

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(P, "LivePipeline", _Pipe)
    args = ["--case", "qa-01-todo-storage", "--case", "qa-03-todo-auth-unanswerable", "--no-judge"]
    return tmp_path, args


def test_write_baseline_saves_the_reference_and_baseline_compares_against_it(cli):
    tmp, args = cli
    ref = tmp / "reference.json"
    assert run_eval.main(args + ["--out", str(tmp / "a.json"), "--write-baseline", str(ref)]) == 0
    saved = json.loads(ref.read_text(encoding="utf-8"))
    assert saved["passed"] == 2 and set(saved["cases"]) == {"qa-01-todo-storage", "qa-03-todo-auth-unanswerable"}
    assert run_eval.main(args + ["--out", str(tmp / "b.json"), "--baseline", str(ref)]) == 0


def test_the_cli_exits_1_on_a_regression_and_2_when_it_cannot_compare(cli, monkeypatch):
    tmp, args = cli
    better = {"created": "2026-11-26", "git_sha": "x", "judge": None, "exec": False, "passed": 2, "total": 2,
              "cases": {"qa-01-todo-storage": "passed", "qa-03-todo-auth-unanswerable": "passed"}}
    (tmp / "ref.json").write_text(json.dumps(better), encoding="utf-8")
    assert run_eval.main(args + ["--out", str(tmp / "c.json"), "--baseline", str(tmp / "ref.json"), "--max-drop", "0"]) == 0

    import evals.pipeline as P
    from tests.test_eval_runner import FakePipeline
    monkeypatch.setattr(P, "LivePipeline", lambda recursion_limit=60: FakePipeline(answer_fn=lambda c: "I have no idea."))
    assert run_eval.main(args + ["--out", str(tmp / "c2.json"), "--baseline", str(tmp / "ref.json"), "--max-drop", "0"]) == 1, \
        "both cases now fail: a drop of 2 with 0 tolerated is a regression"
    worse_ref = {**better, "cases": {**better["cases"], "qa-04-todo-missing-id": "passed"}, "passed": 3, "total": 3}
    (tmp / "ref2.json").write_text(json.dumps(worse_ref), encoding="utf-8")
    assert run_eval.main(args + ["--out", str(tmp / "d.json"), "--baseline", str(tmp / "ref2.json")]) == 2, "different cases"


def test_a_run_that_stopped_early_is_not_saved_as_the_reference(cli, monkeypatch):
    import evals.pipeline as P
    from tests.test_eval_runner import REAL_GROQ_DAILY_429, FlakyProvider

    tmp, args = cli
    monkeypatch.setattr(P, "LivePipeline", lambda recursion_limit=60: FlakyProvider(failures=99, message=REAL_GROQ_DAILY_429))
    assert run_eval.main(args + ["--out", str(tmp / "e.json"), "--write-baseline", str(tmp / "ref.json")]) == 2
    assert not (tmp / "ref.json").exists()


# ------------------------------------------------------------------ the workflow file

def _workflow():
    return yaml.safe_load((ROOT / ".github/workflows/evals.yml").read_text(encoding="utf-8"))


def test_the_gate_only_runs_when_pressed():
    triggers = _workflow().get("on", _workflow().get(True))       # YAML 1.1 reads a bare `on` as True
    assert set(triggers) == {"workflow_dispatch"}, "a full run costs ~92k Groq tokens: never on push or schedule"


def test_the_gate_runs_the_agreed_configuration_against_the_saved_reference():
    text = (ROOT / ".github/workflows/evals.yml").read_text(encoding="utf-8")
    step = next(s["run"] for s in _workflow()["jobs"]["evals"]["steps"] if "evals.run_eval" in str(s.get("run", "")))
    for flag in ("--exec", "--judge-model gemini-3.5-flash-lite", "--baseline evals/baselines/reference.json", "--max-drop 2"):
        assert flag in step, flag
    assert "--case" not in step and "--suite" not in step, "all 15 cases"
    assert "${{ secrets.GROQ_API_KEY_TEST }}" in text and "${{ secrets.GOOGLE_API_KEY }}" in text
    assert "gsk_" not in text and "AIza" not in text, "no literal keys in the workflow"


def test_the_report_is_attached_even_when_the_gate_fails():
    upload = next(s for s in _workflow()["jobs"]["evals"]["steps"] if "upload-artifact" in str(s.get("uses", "")))
    assert upload["if"] == "always()" and upload["with"]["path"] == "eval-report.json"


def test_the_gate_installs_pytest_because_some_exec_checks_run_the_projects_own_tests():
    """The first CI run failed gen-05 "its own tests pass" with "No module named pytest": the runner only had
    requirements.txt, while the reference was produced on a machine with pytest."""
    installs = [s["run"] for s in _workflow()["jobs"]["evals"]["steps"] if "pip install" in str(s.get("run", ""))]
    assert any("requirements-test.txt" in cmd for cmd in installs), installs
    assert "pytest" in (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
