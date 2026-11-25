"""The eval runner, scoring and report, driven by a fake pipeline (no LLM, no network)."""
import json
from pathlib import Path

import pytest

from evals import dataset as D
from evals import run_eval
from evals import runner as R
from evals.evaluators.outcome import Outcome

CASES = {c["id"]: c for c in D.load_cases()}


class FakePipeline:
    """Applies a canned behaviour instead of calling an LLM. Override `edit_fn` etc. per test."""

    def __init__(self, edit_fn=None, answer_fn=None, generate_fn=None, fail_on=()):
        self.edit_fn, self.answer_fn, self.generate_fn = edit_fn, answer_fn, generate_fn
        self.fail_on = set(fail_on)
        self.indexed, self.cleaned, self.workdirs = [], [], []

    def _metrics(self):
        return {"llm_calls": 3, "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001, "retries": 0, "latency_ms": 10.0,
                "per_agent": {"coder": {"calls": 3}}}

    def generate(self, case, workdir, session_id):
        if case["id"] in self.fail_on:
            return {"success": False, "error": "boom"}
        for p, t in (self.generate_fn(case) if self.generate_fn else case["solution"]).items():
            (workdir / p).parent.mkdir(parents=True, exist_ok=True)
            (workdir / p).write_text(t, encoding="utf-8")
        return {"success": True, "metrics": self._metrics(), "integration_fixes": 1}

    def edit(self, case, workdir, session_id, collection):
        self.workdirs.append(workdir)
        if case["id"] in self.fail_on:
            raise RuntimeError("pipeline exploded")
        for p, t in (self.edit_fn(case) if self.edit_fn else case["solution"]).items():
            (workdir / p).parent.mkdir(parents=True, exist_ok=True)
            (workdir / p).write_text(t, encoding="utf-8")
        return {"success": True, "metrics": self._metrics(), "result": {"integration_fixes": 0}}

    def answer(self, case, workdir, session_id, collection):
        if case["id"] in self.fail_on:
            return {"success": False, "error": "llm down"}
        a = self.answer_fn(case) if self.answer_fn else case["reference"]
        return {"success": True, "answer": a, "metrics": self._metrics()}

    def index(self, fixture_dir, collection):
        self.indexed.append((Path(fixture_dir).name, collection))

    def retrieve(self, question, collection, k):
        case = next(c for c in CASES.values() if c["prompt"] == question and c["mode"] == "question_answering")
        return [(s, "chunk") for s in case["expect"]["sources"]]

    def cleanup(self, collections):
        self.cleaned.extend(collections)

    def describe(self):
        return {"provider": "fake", "model": "fake-1"}


class FixedJudge:
    def __init__(self, passed=True):
        self.passed, self.calls = passed, []

    def judge_code(self, case, after, before=None):
        self.calls.append(("code", case["id"]))
        return Outcome("judge", "judge", self.passed, "stub", score=0.9 if self.passed else 0.4)

    def judge_answer(self, case, answer, context):
        self.calls.append(("answer", case["id"]))
        return Outcome("judge", "judge", self.passed, "stub", score=0.9 if self.passed else 0.4)


def run(case_ids, pipeline=None, judge=None, **kw):
    rn = R.Runner(pipeline or FakePipeline(), judge=judge, log=lambda *_: None, run_id="t1", **kw)
    try:
        return rn, rn.run([CASES[i] for i in case_ids], **({"repeat": kw.pop("repeat")} if "repeat" in kw else {}))
    finally:
        rn.close()


# ------------------------------------------------------------------- scoring a case

def test_a_correct_generation_passes_and_records_metrics():
    rn, (r,) = run(["gen-04-wordfreq"], run_exec=True)
    assert r.status == "passed", r.outcomes
    assert r.metrics["llm_calls"] == 3 and r.metrics["integration_fixes"] == 1 and r.files_changed == ["wordfreq.py"]


def test_a_correct_edit_passes():
    _, (r,) = run(["edit-04-truncate-bug"], run_exec=True)
    assert r.status == "passed", [o for o in r.outcomes if o["passed"] is False]
    assert r.files_changed == ["strings.py"] and r.metrics["integration_fixes"] == 0


def test_an_edit_that_changes_nothing_fails_on_modified():
    _, (r,) = run(["edit-04-truncate-bug"], FakePipeline(edit_fn=lambda c: {}))
    assert r.status == "failed" and "modified" in [o["name"] for o in r.outcomes if o["passed"] is False]


def test_an_edit_that_clobbers_an_unrelated_file_fails_the_surgical_check():
    def sloppy(case):
        return {**case["solution"], "mathx.py": "# rewritten for no reason\n"}
    _, (r,) = run(["edit-04-truncate-bug"], FakePipeline(edit_fn=sloppy))
    failed = {o["name"] for o in r.outcomes if o["passed"] is False}
    assert r.status == "failed" and "unmodified" in failed


def test_an_edit_that_breaks_an_import_fails_even_if_the_requested_function_exists():
    def broken(case):
        return {**case["solution"], "main.py": case["solution"]["main.py"].replace("from models import Todo, TodoCreate", "from models import Todo, TodoMake")}
    _, (r,) = run(["edit-01-todo-delete"], FakePipeline(edit_fn=broken))
    assert r.status == "failed" and "imports_resolve" in [o["name"] for o in r.outcomes if o["passed"] is False]


def test_exec_checks_run_only_when_asked():
    _, (off,) = run(["edit-04-truncate-bug"])
    assert any(o["kind"] == "exec" and o["passed"] is None for o in off.outcomes)
    wrong = FakePipeline(edit_fn=lambda c: {"strings.py": D.fixture_files("text_utils")["strings.py"] + "\n# touched\n"})
    _, (on,) = run(["edit-04-truncate-bug"], wrong, run_exec=True)
    assert on.status == "failed" and any(o["kind"] == "exec" and o["passed"] is False for o in on.outcomes)


def test_qa_passes_with_the_reference_answer_and_fails_with_a_wrong_one():
    _, (good,) = run(["qa-01-todo-storage"])
    assert good.status == "passed" and good.answer
    _, (bad,) = run(["qa-01-todo-storage"], FakePipeline(answer_fn=lambda c: "It is stored in Postgres via SQLAlchemy."))
    assert bad.status == "failed"


def test_a_retrieval_miss_is_reported_but_does_not_fail_a_correct_answer():
    class Misses(FakePipeline):
        def retrieve(self, question, collection, k):
            return [("README.md", "unrelated")]
    _, (r,) = run(["qa-01-todo-storage"], Misses())
    retrieval = next(o for o in r.outcomes if o["kind"] == "retrieval")
    assert retrieval["passed"] is False and r.status == "passed"


def test_an_empty_answer_fails():
    _, (r,) = run(["qa-01-todo-storage"], FakePipeline(answer_fn=lambda c: "   "))
    assert r.status == "failed" and "non_empty_answer" in [o["name"] for o in r.outcomes if o["passed"] is False]


# -------------------------------------------------------------------------- errors

def test_a_pipeline_failure_is_an_error_not_a_pass_and_the_suite_continues():
    rn, results = run(["edit-04-truncate-bug", "qa-01-todo-storage"], FakePipeline(fail_on=["edit-04-truncate-bug"]))
    assert [r.status for r in results] == ["error", "passed"]
    assert "pipeline exploded" in results[0].error


def test_a_failed_result_dict_is_an_error():
    _, (r,) = run(["qa-01-todo-storage"], FakePipeline(fail_on=["qa-01-todo-storage"]))
    assert r.status == "error" and "llm down" in r.error


# --------------------------------------------------------------------------- judge

def test_a_failing_judge_fails_an_otherwise_perfect_case():
    _, (r,) = run(["edit-04-truncate-bug"], judge=FixedJudge(passed=False))
    assert r.status == "failed" and [o for o in r.outcomes if o["kind"] == "judge"][0]["passed"] is False


def test_an_unavailable_judge_does_not_fail_the_case():
    class Down(FixedJudge):
        def judge_code(self, *a, **k):
            return Outcome("judge", "judge", None, "judge unavailable", required=False)
    _, (r,) = run(["edit-04-truncate-bug"], judge=Down())
    assert r.status == "passed"


def test_judge_skip_is_honoured_and_each_mode_calls_the_right_judge_method():
    judge = FixedJudge()
    skip_case = {**CASES["edit-04-truncate-bug"], "judge": {"skip": True}}
    rn = R.Runner(FakePipeline(), judge=judge, log=lambda *_: None)
    rn.run([skip_case, CASES["edit-06-median"], CASES["qa-01-todo-storage"], CASES["gen-04-wordfreq"]])
    rn.close()
    assert judge.calls == [("code", "edit-06-median"), ("answer", "qa-01-todo-storage"), ("code", "gen-04-wordfreq")]


# --------------------------------------------------------------- isolation / hygiene

def test_each_fixture_is_indexed_once_per_run_under_a_run_scoped_collection_and_cleaned_up():
    pipe = FakePipeline()
    rn, _ = run(["edit-04-truncate-bug", "edit-06-median", "qa-01-todo-storage", "edit-01-todo-delete"], pipe)
    assert sorted(pipe.indexed) == [("text_utils", "eval_t1_text_utils"), ("todo_api", "eval_t1_todo_api")]
    assert sorted(pipe.cleaned) == ["eval_t1_text_utils", "eval_t1_todo_api"]


def test_edits_happen_on_a_scratch_copy_and_never_touch_the_fixture():
    before = D.fixture_files("text_utils")
    pipe = FakePipeline()
    run(["edit-04-truncate-bug", "edit-06-median"], pipe)
    assert D.fixture_files("text_utils") == before
    assert all(not p.exists() for p in pipe.workdirs), "scratch directories must be removed"


# ---------------------------------------------------------------- repeats / summary

def test_repeat_runs_each_case_n_times_and_flags_flaky_cases():
    answers = iter(["Todos are in todos.json (JSON file).", "It uses Postgres.", "Todos are in todos.json (JSON file)."])
    pipe = FakePipeline(answer_fn=lambda c: next(answers))
    rn = R.Runner(pipe, log=lambda *_: None)
    results = rn.run([CASES["qa-01-todo-storage"]], repeat=3)
    rn.close()
    assert [r.attempt for r in results] == [1, 2, 3] and [r.status for r in results] == ["passed", "failed", "passed"]
    assert R.summarize(results)["flaky_cases"] == ["qa-01-todo-storage"]


def test_summary_aggregates_rates_cost_and_failing_checks_and_counts_errors_against_the_pass_rate():
    rn, results = run(["edit-04-truncate-bug", "edit-06-median", "qa-01-todo-storage", "qa-05-todo-get-before-create"],
                      FakePipeline(edit_fn=lambda c: {} if c["id"] == "edit-06-median" else c["solution"],
                                   fail_on=["qa-05-todo-get-before-create"]), run_exec=True)
    s = R.summarize(results)
    o = s["overall"]
    assert (o["cases"], o["passed"], o["failed"], o["errors"]) == (4, 2, 1, 1)
    assert o["pass_rate"] == 0.5, "errors count against the pass rate"
    assert s["by_mode"]["editing"]["pass_rate"] == 0.5 and s["by_mode"]["question_answering"]["errors"] == 1
    assert o["llm_calls"] == 9 and o["cost_usd"] == pytest.approx(0.003)
    assert "modified" in s["failing_checks"]
    assert "pass" in R.format_summary(s)


def test_judge_rates_are_reported_separately_from_structural_rates():
    rn, results = run(["edit-04-truncate-bug", "qa-01-todo-storage"], judge=FixedJudge(passed=False), run_exec=True)
    o = R.summarize(results)["overall"]
    assert o["structural_pass_rate"] == 1.0 and o["judge_pass_rate"] == 0.0 and o["pass_rate"] == 0.0
    assert o["retrieval_hit_rate"] == 1.0


# ------------------------------------------------------------------------------ CLI

def test_select_cases_filters_by_suite_and_id_and_rejects_unknown_ids():
    cases = D.load_cases()
    assert {c["mode"] for c in run_eval.select_cases("editing", [], cases)} == {"editing"}
    assert [c["id"] for c in run_eval.select_cases("all", ["qa-01-todo-storage"], cases)] == ["qa-01-todo-storage"]
    with pytest.raises(SystemExit):
        run_eval.select_cases("all", ["nope"], cases)


def test_cli_writes_a_report_and_the_min_pass_rate_gate_sets_the_exit_code(tmp_path, monkeypatch):
    import dotenv
    import evals.pipeline as P

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(P, "LivePipeline", lambda recursion_limit=60: FakePipeline(answer_fn=lambda c: "Postgres."))
    out = tmp_path / "r.json"
    code = run_eval.main(["--case", "qa-01-todo-storage", "--no-judge", "--out", str(out), "--label", "unit", "--min-pass-rate", "0.5"])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1, "a 0% pass rate must fail a 50% gate"
    assert report["meta"]["label"] == "unit" and report["meta"]["agent"] == {"provider": "fake", "model": "fake-1"}
    assert report["meta"]["judge"] is None and report["cases"][0]["id"] == "qa-01-todo-storage"
    assert report["summary"]["overall"]["pass_rate"] == 0.0

    monkeypatch.setattr(P, "LivePipeline", lambda recursion_limit=60: FakePipeline())
    assert run_eval.main(["--case", "qa-01-todo-storage", "--no-judge", "--out", str(out), "--min-pass-rate", "0.5"]) == 0


# ------------------------------------------------- judge budget, coverage, checkpoints

def test_cases_that_already_failed_a_deterministic_check_are_not_judged_by_default():
    """Judge calls are scarce (free-tier quotas are tiny); a failed case has failed whatever the judge says."""
    judge = FixedJudge()
    pipe = FakePipeline(edit_fn=lambda c: {} if c["id"] == "edit-06-median" else c["solution"])
    rn = R.Runner(pipe, judge=judge, log=lambda *_: None)
    results = rn.run([CASES["edit-04-truncate-bug"], CASES["edit-06-median"]])
    rn.close()
    assert judge.calls == [("code", "edit-04-truncate-bug")]
    skipped = [o for o in results[1].outcomes if o["kind"] == "judge"][0]
    assert skipped["passed"] is None and skipped["detail"].startswith("not judged")
    assert results[1].status == "failed"


def test_judge_all_also_judges_failed_cases():
    judge = FixedJudge()
    rn = R.Runner(FakePipeline(edit_fn=lambda c: {}), judge=judge, log=lambda *_: None, judge_failed_cases=True)
    rn.run([CASES["edit-06-median"]])
    rn.close()
    assert judge.calls == [("code", "edit-06-median")]


def test_summary_reports_how_much_of_the_run_the_judge_actually_covered():
    class Down(FixedJudge):
        def judge_code(self, *a, **k):
            return Outcome("judge", "judge", None, "judge unavailable: quota exhausted", required=False)

    pipe = FakePipeline(edit_fn=lambda c: {} if c["id"] == "edit-06-median" else c["solution"])
    rn = R.Runner(pipe, judge=Down(), log=lambda *_: None)
    results = rn.run([CASES["edit-04-truncate-bug"], CASES["edit-06-median"]])
    rn.close()
    o = R.summarize(results)["overall"]
    assert (o["judge_judged"], o["judge_not_judged"], o["judge_unavailable"]) == (0, 1, 1)
    assert o["judge_pass_rate"] is None, "an unjudged run must not look like a 100% (or 0%) judge pass rate"
    assert "1 unavailable" in R.format_summary(R.summarize(results))


def test_on_result_is_called_after_every_case_with_the_results_so_far():
    seen = []
    rn = R.Runner(FakePipeline(), log=lambda *_: None)
    rn.run([CASES["qa-01-todo-storage"], CASES["qa-05-todo-get-before-create"]], on_result=lambda rs: seen.append(len(rs)))
    rn.close()
    assert seen == [1, 2]


def test_a_killed_run_keeps_its_checkpointed_report(tmp_path, monkeypatch):
    import dotenv
    import evals.pipeline as P

    class Dies(FakePipeline):
        def answer(self, case, workdir, session_id, collection):
            if case["id"] == "qa-05-todo-get-before-create":
                raise KeyboardInterrupt            # e.g. the process is killed mid-case
            return super().answer(case, workdir, session_id, collection)

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(P, "LivePipeline", lambda recursion_limit=60: Dies())
    out = tmp_path / "partial.json"
    with pytest.raises(KeyboardInterrupt):
        run_eval.main(["--case", "qa-01-todo-storage", "--case", "qa-05-todo-get-before-create", "--no-judge", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["meta"]["complete"] is False
    assert [c["id"] for c in report["cases"]] == ["qa-01-todo-storage"], "the finished case must survive the kill"


# ----------------------------------------------- provider rate limits are not agent failures

REAL_GROQ_429 = ("Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_x` "
                 "service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 6105, Requested 2426. "
                 "Please try again in 3.9825s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}")


def test_provider_trouble_is_distinguished_from_agent_failure():
    assert R.is_infrastructure_error(REAL_GROQ_429)
    assert R.is_infrastructure_error("503 This model is currently experiencing high demand")
    assert R.is_infrastructure_error("ReadTimeout: timed out")
    assert not R.is_infrastructure_error("SyntaxError: invalid syntax")
    assert not R.is_infrastructure_error("KeyError: 'plan'")


def test_a_per_minute_token_limit_waits_a_full_window_not_just_the_hint():
    assert R.retry_wait_seconds(REAL_GROQ_429) == 65.0
    assert R.retry_wait_seconds("429 overloaded. Please retry in 12s") == 20.0            # hint (12+5) below the floor
    assert R.retry_wait_seconds("429 try again in 45s") == 50.0                           # a long hint is honoured
    assert R.retry_wait_seconds("503 unavailable") == 20.0


class FlakyProvider(FakePipeline):
    """Fails with a rate limit `n` times, then behaves."""

    def __init__(self, failures, message=REAL_GROQ_429, **kw):
        super().__init__(**kw)
        self.failures, self.message, self.attempts = failures, message, 0

    def answer(self, case, workdir, session_id, collection):
        self.attempts += 1
        if self.attempts <= self.failures:
            return {"success": False, "error": self.message}
        return super().answer(case, workdir, session_id, collection)


def test_a_rate_limited_case_is_retried_after_the_wait_and_then_counts_as_a_normal_result():
    sleeps = []
    pipe = FlakyProvider(failures=1)
    rn = R.Runner(pipe, log=lambda *_: None, sleep=sleeps.append)
    (r,) = rn.run([CASES["qa-01-todo-storage"]])
    rn.close()
    assert r.status == "passed" and r.infra_retries == 1 and pipe.attempts == 2
    assert sleeps == [65.0]


def test_a_persistently_rate_limited_case_is_an_error_not_a_quality_failure():
    pipe = FlakyProvider(failures=99)
    rn = R.Runner(pipe, log=lambda *_: None, sleep=lambda s: None, infra_retries=2)
    (r,) = rn.run([CASES["qa-01-todo-storage"]])
    rn.close()
    assert r.status == "error" and r.infra_retries == 2 and pipe.attempts == 3
    o = R.summarize([r])["overall"]
    assert o["errors"] == 1 and o["failed"] == 0 and o["infra_retries"] == 2


def test_a_genuine_agent_error_is_not_retried():
    pipe = FlakyProvider(failures=99, message="KeyError: 'plan'")
    sleeps = []
    rn = R.Runner(pipe, log=lambda *_: None, sleep=sleeps.append)
    (r,) = rn.run([CASES["qa-01-todo-storage"]])
    rn.close()
    assert r.status == "error" and r.infra_retries == 0 and pipe.attempts == 1 and sleeps == []


def test_retries_can_be_disabled():
    pipe = FlakyProvider(failures=1)
    rn = R.Runner(pipe, log=lambda *_: None, sleep=lambda s: None, infra_retries=0)
    (r,) = rn.run([CASES["qa-01-todo-storage"]])
    rn.close()
    assert r.status == "error" and pipe.attempts == 1


def test_the_summary_makes_provider_trouble_visible():
    pipe = FlakyProvider(failures=1)
    rn = R.Runner(pipe, log=lambda *_: None, sleep=lambda s: None)
    results = rn.run([CASES["qa-01-todo-storage"]])
    rn.close()
    assert "provider rate limits / overload: 1 retry across 1 case(s)" in R.format_summary(R.summarize(results))


# --------------------------------------------- a failure keeps what the agent wrote (scratch dirs are deleted)

def test_a_failed_generation_keeps_the_files_the_agent_wrote():
    pipe = FakePipeline(generate_fn=lambda c: {"main.py": "def broken(:\n", "README.md": "# hi\n"})
    rn = R.Runner(pipe, log=lambda *_: None)
    (r,) = rn.run([CASES["gen-04-wordfreq"]])
    rn.close()
    assert r.status == "failed"
    assert r.output_files["main.py"] == "def broken(:\n" and "README.md" in r.output_files
    assert r.to_dict()["output_files"]["main.py"] == "def broken(:\n", "it must reach the JSON report"


def test_a_failed_edit_keeps_only_the_files_that_changed():
    case = CASES["edit-04-truncate-bug"]
    pipe = FakePipeline(edit_fn=lambda c: {"strings.py": "def truncate(:\n"})
    rn = R.Runner(pipe, log=lambda *_: None)
    (r,) = rn.run([case])
    rn.close()
    assert r.status == "failed" and list(r.output_files) == ["strings.py"]


def test_a_passing_case_keeps_no_output():
    rn = R.Runner(FakePipeline(edit_fn=lambda c: c["solution"]), log=lambda *_: None)
    (r,) = rn.run([CASES["edit-04-truncate-bug"]])
    rn.close()
    assert r.status == "passed" and r.output_files == {}


def test_kept_output_is_truncated_per_file():
    pipe = FakePipeline(generate_fn=lambda c: {"main.py": "x = 1\n" * 20_000})
    rn = R.Runner(pipe, log=lambda *_: None)
    (r,) = rn.run([CASES["gen-04-wordfreq"]])
    rn.close()
    assert r.status == "failed" and len(r.output_files["main.py"]) == R.MAX_KEPT_FILE_CHARS


# ------------------------------------- a daily provider quota stops the run instead of failing every case

REAL_GROQ_DAILY_429 = ("Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_x` "
                       "service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199400, Requested 2098. "
                       "Please try again in 10m47.136s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}")


def test_a_daily_token_limit_stops_the_run_without_retrying_or_running_the_rest():
    """The live repeat run spent ~25 minutes turning 17 cases into identical 429 errors (waiting 20s twice per case)."""
    sleeps = []
    pipe = FlakyProvider(failures=99, message=REAL_GROQ_DAILY_429)
    logs = []
    rn = R.Runner(pipe, log=logs.append, sleep=sleeps.append)
    results = rn.run([CASES["qa-01-todo-storage"], CASES["qa-03-todo-auth-unanswerable"], CASES["qa-04-todo-missing-id"]])
    rn.close()
    assert [r.status for r in results] == ["error"], "the later cases must not be attempted"
    assert pipe.attempts == 1 and sleeps == [] and results[0].infra_retries == 0
    assert "tokens per day" in rn.stopped_early and any("STOPPED after 1 of 3" in m for m in logs)


def test_a_per_minute_limit_still_retries_and_does_not_stop_the_run():
    pipe = FlakyProvider(failures=1)                                  # the per-minute Groq error from earlier tests
    rn = R.Runner(pipe, log=lambda *_: None, sleep=lambda s: None)
    results = rn.run([CASES["qa-01-todo-storage"], CASES["qa-03-todo-auth-unanswerable"]])
    rn.close()
    assert [r.status for r in results] == ["passed", "passed"] and rn.stopped_early is None


def test_the_report_says_when_the_run_stopped_early(tmp_path, monkeypatch):
    import dotenv
    import evals.pipeline as P

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(P, "LivePipeline", lambda recursion_limit=60: FlakyProvider(failures=99, message=REAL_GROQ_DAILY_429))
    out = tmp_path / "r.json"
    run_eval.main(["--case", "qa-01-todo-storage", "--case", "qa-03-todo-auth-unanswerable", "--no-judge", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert "tokens per day" in report["meta"]["stopped_early"]
    assert report["meta"]["cases_requested"] == ["qa-01-todo-storage", "qa-03-todo-auth-unanswerable"]
    assert len(report["cases"]) == 1
