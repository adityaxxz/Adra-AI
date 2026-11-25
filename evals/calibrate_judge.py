"""Check the LLM judge against labelled good/bad outputs (real model calls: one per item, 20 items).

    python -m evals.calibrate_judge [--model gemini-3.5-flash-lite]

Mind the provider's quota: Gemini's free tier allows very few requests per day per model.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from evals.keys import use_test_keys  # noqa: E402

use_test_keys()                     # judge on GOOGLE_API_KEY_TEST when set, like the eval runs

from evals.calibration import ITEMS, run_calibration  # noqa: E402
from evals.evaluators.judge import JUDGE_MODEL, Judge  # noqa: E402


def _show(r: dict) -> None:
    mark = "ok " if r["agrees"] else ("?? " if r["passed"] is None else "BAD")
    verdict = "pass" if r["passed"] else "fail" if r["passed"] is False else "n/a"
    print(f"  {mark} {r['id']:28s} label={r['expect']:4s} judge={verdict}  {r['detail'][:150]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=JUDGE_MODEL)
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    judge = Judge(model=args.model)
    print(f"judge model: {args.model}  ({len(ITEMS)} items)")
    result = run_calibration(judge, on_row=_show)
    print(f"\nagreement: {result['agreement']:.0%} ({result['judged']} judged of {result['total']}); "
          f"judge calls={judge.calls} tokens in/out={judge.input_tokens}/{judge.output_tokens} rate-limit hits={judge.rate_limit_hits}")
    if judge.exhausted:
        print(f"WARNING: stopped early - {judge.exhausted}. Items after that point are 'n/a', not agreement.")
    return 0 if result["agreement"] >= 0.9 and result["judged"] == result["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
