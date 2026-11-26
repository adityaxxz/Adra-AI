"""Run the golden dataset through the real agent pipelines and score the results.

    python -m evals.run_eval                          # every case, structural + LLM judge
    python -m evals.run_eval --suite editing --exec   # one mode, also run the cases' executable checks
    python -m evals.run_eval --case edit-04-truncate-bug --case qa-01-todo-storage
    python -m evals.run_eval --no-judge --repeat 3    # structural only, 3 attempts per case (flakiness)

Costs real LLM/embedding calls, and `--exec` runs LLM-generated code on this machine (stripped
environment, temp dir, timeout - but NOT a sandbox). Reports are written to evals/reports/.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SUITES = {"all": None, "generation": "generation", "editing": "editing", "qa": "question_answering"}


def select_cases(suite: str, ids: list, cases: list) -> list:
    picked = [c for c in cases if SUITES[suite] is None or c["mode"] == SUITES[suite]]
    if ids:
        known = {c["id"] for c in cases}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise SystemExit(f"unknown case id(s): {unknown}")
        picked = [c for c in cases if c["id"] in ids]
    return picked


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:                                      # noqa: BLE001
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", choices=list(SUITES), default="all")
    ap.add_argument("--case", action="append", default=[], help="run only this case id (repeatable)")
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM judge (structural checks only)")
    ap.add_argument("--judge-model", help="override the judge model (default: $EVAL_JUDGE_MODEL or gemini-3.5-flash-lite)")
    ap.add_argument("--judge-all", action="store_true",
                    help="also judge cases that already failed a deterministic check (spends more judge calls)")
    ap.add_argument("--exec", action="store_true", dest="run_exec", help="run each case's executable checks (executes generated code)")
    ap.add_argument("--repeat", type=int, default=1, help="attempts per case, to measure flakiness")
    ap.add_argument("--recursion-limit", type=int, default=60)
    ap.add_argument("--infra-retries", type=int, default=2,
                    help="re-run a case this many times when it fails on provider rate limits/overload (default 2)")
    ap.add_argument("--min-interval", type=float,
                    help="seconds between LLM calls (sets LLM_MIN_INTERVAL_SEC); raise it for providers with a tokens-per-minute cap")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", help="report path (default: evals/reports/<timestamp>-<label>.json)")
    ap.add_argument("--min-pass-rate", type=float, help="exit 1 if the overall pass rate is below this (0-1)")
    ap.add_argument("--baseline", help="compare with this saved reference run (exit 1 = regression, 2 = can't compare)")
    ap.add_argument("--max-drop", type=int, default=2, help="with --baseline: how many fewer passing cases are tolerated (default 2)")
    ap.add_argument("--write-baseline", help="save this run as the reference at this path (e.g. evals/baselines/reference.json)")
    args = ap.parse_args(argv)

    # Line-buffered, so progress is visible while it runs and a killed run loses nothing already printed.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if args.min_interval is not None:
        os.environ["LLM_MIN_INTERVAL_SEC"] = str(args.min_interval)   # set first: dotenv never overrides it

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")                             # before any agent import: they read keys at import time
    from evals.keys import use_test_keys

    test_keys = use_test_keys()                            # evals run on the *_TEST keys when set, so they never drain the app's quota

    from agent.prompts import PROMPT_VERSIONS
    from evals.dataset import load_cases
    from evals.evaluators.judge import JUDGE_MODEL, Judge
    from evals.pipeline import LivePipeline
    from evals.runner import Runner, format_summary, summarize

    cases = select_cases(args.suite, args.case, load_cases())
    if not cases:
        raise SystemExit("no cases selected")

    pipeline = LivePipeline(recursion_limit=args.recursion_limit)
    judge_model = args.judge_model or JUDGE_MODEL
    judge = None if args.no_judge else Judge(model=judge_model)
    runner = Runner(pipeline, judge=judge, run_exec=args.run_exec, judge_failed_cases=args.judge_all,
                    infra_retries=args.infra_retries)
    started = datetime.now(timezone.utc)
    out = Path(args.out) if args.out else ROOT / "evals" / "reports" / f"{started:%Y%m%d-%H%M%S}-{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    def build_report(results: list, complete: bool) -> dict:
        return {
            "meta": {"run_id": runner.run_id, "label": args.label, "started": started.isoformat(), "complete": complete,
                     "wall_seconds": round(time.monotonic() - t0, 1), "git_sha": git_sha(), "agent": pipeline.describe(),
                     "prompt_versions": dict(PROMPT_VERSIONS),
                     "judge": None if judge is None else judge_model,
                     "judge_usage": None if judge is None else {"calls": judge.calls, "input_tokens": judge.input_tokens,
                                                                 "output_tokens": judge.output_tokens, "rate_limit_hits": judge.rate_limit_hits,
                                                                 "quota_exhausted": judge.exhausted},
                     "stopped_early": runner.stopped_early, "test_keys": test_keys,
                     "exec": args.run_exec, "repeat": args.repeat, "infra_retries": args.infra_retries,
                     "min_interval": os.environ.get("LLM_MIN_INTERVAL_SEC"), "suite": args.suite, "cases_requested": [c["id"] for c in cases]},
            "summary": summarize(results),
            "cases": [r.to_dict() for r in results],
        }

    def checkpoint(results: list) -> None:
        out.write_text(json.dumps(build_report(results, complete=False), indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"run {runner.run_id}: {len(cases)} case(s) x{args.repeat}  agent={pipeline.describe()}  "
          f"judge={'off' if judge is None else judge_model}  exec={'on' if args.run_exec else 'off'}  report={out}\n")
    results: list = []
    try:
        results = runner.run(cases, repeat=args.repeat, on_result=lambda rs: (results.__setitem__(slice(None), rs), checkpoint(rs)))
    finally:
        runner.close()
    report = build_report(results, complete=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + format_summary(report["summary"]))
    if judge is not None and judge.exhausted:
        print(f"\nWARNING: judge stopped early - {judge.exhausted}. Unjudged cases are reported as 'unavailable', not as passes.")
    if runner.stopped_early:
        print(f"\nWARNING: stopped early - {runner.stopped_early[:200]}. The remaining cases were NOT run; this is not a full result.")
    print(f"\nreport: {out}")
    code = 0
    if args.write_baseline:
        from evals.baseline import run_problems, write_baseline

        blockers = run_problems(report)
        if blockers:
            print("NOT saved as the reference, because: " + "; ".join(blockers))
            code = 2
        else:
            saved = write_baseline(report, args.write_baseline)
            print(f"saved as the reference: {args.write_baseline} ({saved['passed']}/{saved['total']} passed)")
    if args.baseline:
        from evals.baseline import EXIT_CODES, compare

        verdict, lines = compare(report, json.loads(Path(args.baseline).read_text(encoding="utf-8")), args.max_drop)
        print("\n" + "\n".join(lines))
        code = max(code, EXIT_CODES[verdict])
    rate = report["summary"]["overall"]["pass_rate"] or 0
    if args.min_pass_rate is not None and rate < args.min_pass_rate:
        print(f"FAIL: pass rate {rate:.0%} is below {args.min_pass_rate:.0%}")
        code = max(code, 1)
    return code


if __name__ == "__main__":
    sys.exit(main())
