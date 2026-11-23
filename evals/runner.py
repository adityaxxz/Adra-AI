"""Run dataset cases through a pipeline, score them, and aggregate a report."""
import re
import shutil
import statistics
import tempfile
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from evals import dataset as D
from evals.evaluators import evaluate as E
from evals.evaluators.outcome import Outcome

QA_K = 5

_INFRA = re.compile(r"429|rate.?limit|resource.?exhausted|too many requests|overloaded|\b50[234]\b|timed? ?out|connection (error|reset|aborted)", re.I)
_TRY_AGAIN = re.compile(r"(?:try again|retry) in ([\d.]+)\s*(ms|s)", re.I)


def is_infrastructure_error(message: str) -> bool:
    """Provider/network trouble (rate limits, overload, timeouts) as opposed to the agent doing its job badly."""
    return bool(_INFRA.search(message or ""))


def retry_wait_seconds(message: str) -> float:
    """How long to wait before retrying: the provider's own hint if it gave one, and a full
    minute for per-minute token limits (their window is 60s, and the hint is for the next request only)."""
    low = (message or "").lower()
    m = _TRY_AGAIN.search(message or "")
    hinted = (float(m.group(1)) / (1000 if m.group(2).lower() == "ms" else 1)) + 5 if m else 20.0
    return max(hinted, 65.0) if ("per minute" in low or "tpm" in low) else max(hinted, 20.0)


@dataclass
class CaseResult:
    id: str
    mode: str
    source: str
    attempt: int = 1
    status: str = "error"            # passed | failed | error
    seconds: float = 0.0
    error: str = ""
    outcomes: list = field(default_factory=list)      # list[dict] (Outcome.to_dict())
    metrics: dict = field(default_factory=dict)       # llm_calls, tokens, cost_usd, retries, integration_fixes
    answer: Optional[str] = None
    files_changed: list = field(default_factory=list)
    infra_retries: int = 0            # times the case was re-run after provider rate limits / overload

    def to_dict(self) -> dict:
        return asdict(self)


class Runner:
    def __init__(self, pipeline, judge=None, run_exec: bool = False, run_id: Optional[str] = None, log=print,
                 judge_failed_cases: bool = False, infra_retries: int = 2, sleep=time.sleep):
        self.pipeline = pipeline
        self.judge = judge
        self.run_exec = run_exec
        # Judge calls are the scarce resource (free-tier quotas are tiny). A case that already failed a
        # deterministic check has failed whatever the judge says, so by default it is not judged.
        self.judge_failed_cases = judge_failed_cases
        self.infra_retries = infra_retries
        self._sleep = sleep
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.log = log
        self._collections: dict = {}          # fixture -> collection name
        self._workdirs: list = []

    # ------------------------------------------------------------------ plumbing
    def _collection(self, fixture: str) -> str:
        if fixture not in self._collections:
            name = f"eval_{self.run_id}_{fixture}"
            self.pipeline.index(D.FIXTURES / fixture, name)
            self._collections[fixture] = name
        return self._collections[fixture]

    def _workdir(self, fixture: Optional[str] = None) -> Path:
        path = Path(tempfile.mkdtemp(prefix="adra_eval_"))
        self._workdirs.append(path)
        if fixture:
            shutil.copytree(D.FIXTURES / fixture, path, dirs_exist_ok=True)
        return path

    def close(self) -> None:
        self.pipeline.cleanup(list(self._collections.values()))
        for p in self._workdirs:
            shutil.rmtree(p, ignore_errors=True)

    # ----------------------------------------------------------------- one case
    def run_case(self, case: dict, attempt: int = 1) -> CaseResult:
        """Run one case. If it errors because of provider rate limits/overload, re-run it after the
        suggested wait (up to `infra_retries` times): that is infrastructure noise, not agent quality.
        The retries are recorded so the exposure stays visible in the report."""
        start = time.monotonic()
        retries = 0
        while True:
            res = self._run_once(case, attempt)
            if res.status == "error" and retries < self.infra_retries and is_infrastructure_error(res.error):
                wait = retry_wait_seconds(res.error)
                retries += 1
                self.log(f"      infrastructure error on {case['id']} ({res.error[:90]}...); retry {retries}/{self.infra_retries} in {wait:.0f}s")
                self._sleep(wait)
                continue
            res.infra_retries = retries
            res.seconds = round(time.monotonic() - start, 1)
            return res

    def _run_once(self, case: dict, attempt: int) -> CaseResult:
        res = CaseResult(id=case["id"], mode=case["mode"], source=case.get("source", ""), attempt=attempt)
        session_id = f"eval-{self.run_id}-{case['id']}-{attempt}-{uuid.uuid4().hex[:4]}"
        try:
            if case["mode"] == "generation":
                self._generation(case, res, session_id)
            elif case["mode"] == "editing":
                self._editing(case, res, session_id)
            else:
                self._qa(case, res, session_id)
        except Exception as e:                      # noqa: BLE001 - a crashing case must not stop the suite
            res.status, res.error = "error", f"{type(e).__name__}: {e}"
            res.outcomes = []
            self.log(traceback.format_exc(limit=3))
        return res

    @staticmethod
    def _metrics(task_result: dict) -> dict:
        m = task_result.get("metrics") or {}
        fixes = task_result.get("integration_fixes")
        if fixes is None:
            fixes = (task_result.get("result") or {}).get("integration_fixes")
        return {"llm_calls": m.get("llm_calls", 0), "input_tokens": m.get("input_tokens", 0), "output_tokens": m.get("output_tokens", 0),
                "cost_usd": m.get("cost_usd", 0.0), "retries": m.get("retries", 0), "llm_latency_ms": m.get("latency_ms", 0.0),
                "integration_fixes": fixes, "per_agent": m.get("per_agent", {})}

    def _finish(self, res: CaseResult, outcomes: list) -> None:
        res.outcomes = [o.to_dict() for o in outcomes]
        failed = [o for o in outcomes if o.required and o.passed is False]
        res.status = "failed" if failed else "passed"

    def _should_judge(self, case, outcomes) -> Optional[Outcome]:
        """None means 'go ahead and judge'; otherwise the skipped Outcome explaining why not."""
        if not self.judge or (case.get("judge") or {}).get("skip"):
            return Outcome("judge", "judge", None, "judge disabled" if not self.judge else "skipped by the case", required=False)
        if not self.judge_failed_cases and any(o.required and o.passed is False for o in outcomes):
            return Outcome("judge", "judge", None, "not judged: a deterministic check already failed", required=False)
        return None

    def _judge_code(self, case, after, before, outcomes):
        skip = self._should_judge(case, outcomes)
        if skip is None:
            outcomes.append(self.judge.judge_code(case, after, before))
        elif self.judge:
            outcomes.append(skip)

    def _generation(self, case, res, session_id):
        workdir = self._workdir()
        out = self.pipeline.generate(case, workdir, session_id)
        res.metrics = self._metrics(out)
        if not out.get("success"):
            res.status, res.error = "error", f"pipeline failed: {out.get('error')}"
            return
        after = D.read_tree(workdir)
        res.files_changed = sorted(after)
        outcomes = E.evaluate_project(case, after, None, run_exec=self.run_exec)
        self._judge_code(case, after, None, outcomes)
        self._finish(res, outcomes)

    def _editing(self, case, res, session_id):
        collection = self._collection(case["fixture"])
        workdir = self._workdir(case["fixture"])
        before = D.read_tree(workdir)
        out = self.pipeline.edit(case, workdir, session_id, collection)
        res.metrics = self._metrics(out)
        if not out.get("success"):
            res.status, res.error = "error", f"pipeline failed: {out.get('error')}"
            return
        after = D.read_tree(workdir)
        res.files_changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        outcomes = E.evaluate_project(case, after, before, run_exec=self.run_exec)
        self._judge_code(case, after, before, outcomes)
        self._finish(res, outcomes)

    def _qa(self, case, res, session_id):
        collection = self._collection(case["fixture"])
        workdir = self._workdir(case["fixture"])
        out = self.pipeline.answer(case, workdir, session_id, collection)
        res.metrics = self._metrics(out)
        if not out.get("success"):
            res.status, res.error = "error", f"pipeline failed: {out.get('error')}"
            return
        answer = out.get("answer") or ""
        res.answer = answer
        k = case["expect"].get("k", QA_K)
        chunks = self.pipeline.retrieve(case["prompt"], collection, k)
        outcomes = E.evaluate_answer(case, answer, [p for p, _ in chunks])
        skip = self._should_judge(case, outcomes)
        if skip is None:
            context = "\n\n".join(f"FILE: {p}\n\n{c}" for p, c in chunks)
            outcomes.append(self.judge.judge_answer(case, answer, context))
        elif self.judge:
            outcomes.append(skip)
        self._finish(res, outcomes)

    # -------------------------------------------------------------------- suite
    def run(self, cases: list, repeat: int = 1, on_result=None) -> list:
        """`on_result(results_so_far)` is called after every case, so a caller can checkpoint a report
        and a killed run loses at most the case in flight."""
        results = []
        total = len(cases) * repeat
        n = 0
        for case in cases:
            for attempt in range(1, repeat + 1):
                n += 1
                r = self.run_case(case, attempt)
                results.append(r)
                if on_result:
                    on_result(results)
                bad = [o["name"] for o in r.outcomes if o["required"] and o["passed"] is False]
                tag = {"passed": "PASS", "failed": "FAIL", "error": "ERR "}[r.status]
                self.log(f"[{n}/{total}] {tag} {r.id}{f' #{attempt}' if repeat > 1 else ''}  {r.seconds:>5.0f}s  "
                         f"calls={r.metrics.get('llm_calls', 0)}  {('failed: ' + ', '.join(bad)) if bad else r.error[:100]}")
        return results


# ------------------------------------------------------------------------- report

def _pct(sorted_values: list, q: float) -> float:
    if not sorted_values:
        return 0.0
    return sorted_values[min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1))))]


def _group(results: list) -> dict:
    def rate(items):
        return round(sum(r.status == "passed" for r in items) / len(items), 3) if items else None

    structural = []
    for r in results:
        req = [o for o in r.outcomes if o["required"] and o["kind"] != "judge"]
        if r.status != "error" and req:
            structural.append(all(o["passed"] is not False for o in req))
    all_judge = [o for r in results for o in r.outcomes if o["kind"] == "judge"]
    judged = [o for o in all_judge if o["passed"] is not None]
    unavailable = sum(o["detail"].startswith("judge unavailable") for o in all_judge)
    not_judged = sum(o["detail"].startswith("not judged") for o in all_judge)
    retrieval = [o for r in results for o in r.outcomes if o["kind"] == "retrieval"]
    secs = sorted(r.seconds for r in results)
    return {
        "cases": len(results),
        "passed": sum(r.status == "passed" for r in results),
        "failed": sum(r.status == "failed" for r in results),
        "errors": sum(r.status == "error" for r in results),
        "pass_rate": rate(results),                      # errors count against the pass rate
        "structural_pass_rate": round(sum(structural) / len(structural), 3) if structural else None,
        "judge_pass_rate": round(sum(o["passed"] for o in judged) / len(judged), 3) if judged else None,
        "judge_judged": len(judged), "judge_not_judged": not_judged, "judge_unavailable": unavailable,
        "judge_mean_score": round(statistics.mean(o["score"] for o in judged if o["score"] is not None), 3) if judged else None,
        "retrieval_hit_rate": round(sum(o["passed"] for o in retrieval) / len(retrieval), 3) if retrieval else None,
        "retrieval_mean_recall": round(statistics.mean(o["score"] for o in retrieval), 3) if retrieval else None,
        "llm_calls": sum(r.metrics.get("llm_calls", 0) for r in results),
        "input_tokens": sum(r.metrics.get("input_tokens", 0) for r in results),
        "output_tokens": sum(r.metrics.get("output_tokens", 0) for r in results),
        "cost_usd": round(sum(r.metrics.get("cost_usd", 0.0) for r in results), 6),
        "retries": sum(r.metrics.get("retries", 0) for r in results),
        "infra_retries": sum(r.infra_retries for r in results),
        "cases_with_infra_retries": sum(1 for r in results if r.infra_retries),
        "seconds_p50": _pct(secs, 0.5), "seconds_p95": _pct(secs, 0.95),
    }


def summarize(results: list) -> dict:
    by_mode = {m: _group([r for r in results if r.mode == m]) for m in D.MODES if any(r.mode == m for r in results)}
    failing = {}
    for r in results:
        for o in r.outcomes:
            if o["required"] and o["passed"] is False:
                failing[o["name"]] = failing.get(o["name"], 0) + 1
    fixes = [r.metrics.get("integration_fixes") for r in results if r.mode in ("generation", "editing") and r.metrics.get("integration_fixes") is not None]
    per_case = {}
    for r in results:
        per_case.setdefault(r.id, []).append(r.status)
    flaky = sorted(c for c, s in per_case.items() if len(s) > 1 and len(set(s)) > 1)
    return {
        "overall": _group(results),
        "by_mode": by_mode,
        "failing_checks": dict(sorted(failing.items(), key=lambda kv: -kv[1])),
        "integration_fixes": {"mean": round(statistics.mean(fixes), 2) if fixes else None, "max": max(fixes) if fixes else None},
        "flaky_cases": flaky,
    }


def format_summary(summary: dict) -> str:
    def row(name, g):
        def f(v):
            return "  -  " if v is None else f"{v:.0%}"
        return (f"{name:<20}{g['cases']:>3} cases  pass {f(g['pass_rate']):>5}  structural {f(g['structural_pass_rate']):>5}  "
                f"judge {f(g['judge_pass_rate']):>5}  retrieval-hit {f(g['retrieval_hit_rate']):>5}  "
                f"${g['cost_usd']:.4f}  p50 {g['seconds_p50']:.0f}s p95 {g['seconds_p95']:.0f}s  err {g['errors']}")
    lines = [row("OVERALL", summary["overall"])]
    lines += [row(f"  {m}", g) for m, g in summary["by_mode"].items()]
    o = summary["overall"]
    if o["infra_retries"]:
        lines.append(f"provider rate limits / overload: {o['infra_retries']} retr{'y' if o['infra_retries'] == 1 else 'ies'} across {o['cases_with_infra_retries']} case(s)")
    if o["judge_judged"] or o["judge_not_judged"] or o["judge_unavailable"]:
        lines.append(f"judge coverage: {o['judge_judged']} judged, {o['judge_not_judged']} not judged (already failed a "
                     f"deterministic check), {o['judge_unavailable']} unavailable")
    if summary["failing_checks"]:
        lines.append("most common failing checks: " + ", ".join(f"{k} x{v}" for k, v in list(summary["failing_checks"].items())[:6]))
    if summary["flaky_cases"]:
        lines.append(f"flaky (pass and fail across repeats): {summary['flaky_cases']}")
    return "\n".join(lines)
