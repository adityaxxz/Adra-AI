"""The saved reference run for §2.4 "Regression gate in CI", and the comparison against it.

AI output varies run to run, so a single failed case is not a regression. The gate fails only when clearly fewer cases
pass than in the saved reference (more than `max_drop`), and it refuses to give a verdict on a run that does not measure
the same thing: one that stopped early, left cases unjudged, or covered a different set of cases.
"""
import json
from pathlib import Path

PASS, REGRESSION, INCONCLUSIVE = "pass", "regression", "inconclusive"
EXIT_CODES = {PASS: 0, REGRESSION: 1, INCONCLUSIVE: 2}


def _statuses(report: dict) -> dict:
    return {c["id"]: c["status"] for c in report["cases"]}


def to_baseline(report: dict) -> dict:
    """A compact reference: which cases passed, and how the run was configured (no outputs or answers)."""
    meta = report["meta"]
    statuses = _statuses(report)
    return {
        "created": meta.get("started"), "git_sha": meta.get("git_sha"), "agent": meta.get("agent"),
        "prompt_versions": meta.get("prompt_versions"), "judge": meta.get("judge"), "exec": meta.get("exec"),
        "passed": sum(s == "passed" for s in statuses.values()), "total": len(statuses),
        "cases": dict(sorted(statuses.items())),
    }


def write_baseline(report: dict, path) -> dict:
    baseline = to_baseline(report)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    return baseline


def run_problems(report: dict) -> list[str]:
    """Reasons this run is not a complete measurement (so it can be neither compared nor saved as the reference)."""
    meta, overall = report["meta"], report["summary"]["overall"]
    out = []
    if not meta.get("complete", True):
        out.append("the run did not finish")
    if meta.get("stopped_early"):
        out.append(f"the run stopped early: {meta['stopped_early'][:120]}")
    if meta.get("repeat", 1) != 1:
        out.append("the reference is one attempt per case; run with --repeat 1")
    if overall.get("judge_unavailable"):
        out.append(f"{overall['judge_unavailable']} case(s) could not be judged (quota?), so passes would be over-counted")
    return out


def problems_with(report: dict, baseline: dict) -> list[str]:
    """Reasons this run cannot be compared with the reference at all."""
    meta = report["meta"]
    out = run_problems(report)
    if baseline.get("judge") and meta.get("judge") != baseline["judge"]:
        out.append(f"judged by {meta.get('judge')}, the reference by {baseline['judge']}")
    if bool(meta.get("exec")) != bool(baseline.get("exec")):
        out.append("executable checks were " + ("on" if meta.get("exec") else "off") + " but not in the reference")
    missing, extra = set(baseline["cases"]) - set(_statuses(report)), set(_statuses(report)) - set(baseline["cases"])
    if missing or extra:
        out.append(f"different cases than the reference (missing {sorted(missing)}, new {sorted(extra)}): update the reference")
    return out


def compare(report: dict, baseline: dict, max_drop: int = 2) -> tuple[str, list[str]]:
    """(verdict, explanation lines). Regression = more than `max_drop` fewer passes than the reference."""
    blockers = problems_with(report, baseline)
    if blockers:
        return INCONCLUSIVE, ["INCONCLUSIVE: this run can't be compared with the saved reference:"] + [f"  - {b}" for b in blockers]
    now, ref = _statuses(report), baseline["cases"]
    passed_now, passed_ref = sum(s == "passed" for s in now.values()), baseline["passed"]
    newly_failing = sorted(c for c in now if ref.get(c) == "passed" and now[c] != "passed")
    newly_passing = sorted(c for c in now if ref.get(c) != "passed" and now[c] == "passed")
    drop = passed_ref - passed_now
    verdict = REGRESSION if drop > max_drop else PASS
    lines = [f"{'REGRESSION' if verdict == REGRESSION else 'OK'}: {passed_now}/{len(now)} passed; the reference "
             f"({baseline.get('created', '?')[:10]}, {(baseline.get('git_sha') or '?')[:8]}) had {passed_ref}/{baseline['total']}; "
             f"allowed drop {max_drop}, actual {drop}"]
    if newly_failing:
        lines.append(f"  now failing: {', '.join(newly_failing)}")
    if newly_passing:
        lines.append(f"  now passing: {', '.join(newly_passing)}")
    lines += prompt_changes(report, baseline)
    return verdict, lines


def prompt_changes(report: dict, baseline: dict) -> list[str]:
    """Which prompt versions differ from the reference. Shown, never blocking: checking a prompt change against the last
    good run is what the gate is for."""
    now, ref = report["meta"].get("prompt_versions"), baseline.get("prompt_versions")
    if not now:
        return []
    if not ref:
        return ["  prompts: the reference was saved before prompt versions were recorded"]
    changed = [f"{name} v{ref.get(name, '?')} -> v{now[name]}" for name in sorted(now) if ref.get(name) != now[name]]
    return [f"  prompts changed since the reference: {', '.join(changed)}"] if changed else ["  prompts: same versions as the reference"]
