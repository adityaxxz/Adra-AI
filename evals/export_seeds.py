"""Export real prompts from `agent_runs` as *candidate* eval cases for one user.

    python -m evals.export_seeds --user-email you@example.com [--database-url ...] [--mode generation]

Privacy: prompts are user content, so this REQUIRES an explicit email and only reads that user's
runs. Output goes to evals/datasets/seed_candidates.yaml, which is not loaded by the suite - a human
reviews each candidate, fills in `fixture`/`expect`, and moves it into generation/editing/qa.yaml.
Prompts the dataset already contains, and the harness's own `eval-*` sessions, are skipped.
"""
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "evals" / "datasets" / "seed_candidates.yaml"
_MODE_NAMES = {"generation": "generation", "editing": "editing", "question_answering": "question_answering"}

_QUERY = """
select r.mode, r.user_prompt, r.status
from agent_runs r
join sessions s on s.id = r.session_id
join users u on u.id = s.user_id
where lower(u.email) = lower($1) and r.session_id not like 'eval-%'
order by r.created_at
"""


def normalise(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt).strip().lower()


def build_candidates(rows: list, existing_prompts: set, mode: str | None = None) -> list[dict]:
    """Unique prompts (first occurrence wins), minus ones the dataset already has."""
    seen = {normalise(p) for p in existing_prompts}
    out, counters = [], {}
    for r in rows:
        key = normalise(r["user_prompt"])
        if not key or key in seen or (mode and r["mode"] != mode):
            continue
        seen.add(key)
        m = r["mode"]
        counters[m] = counters.get(m, 0) + 1
        case = {"id": f"seed-{m.split('_')[0]}-{counters[m]:02d}", "mode": m, "source": "seeded-export",
                "prompt": r["user_prompt"].strip(), "needs_review": True}
        if m in ("editing", "question_answering"):
            case["fixture"] = None            # these refer to the user's own repository: pick or build a fixture for it
            case["expect"] = {}
        out.append(case)
    return out


async def fetch_rows(dsn: str, email: str) -> list:
    import asyncpg

    conn = await asyncpg.connect(dsn.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        return [dict(r) for r in await conn.fetch(_QUERY, email)]
    finally:
        await conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-email", required=True, help="only this user's runs are read (explicit opt-in)")
    ap.add_argument("--database-url", default=None, help="default: $DATABASE_URL")
    ap.add_argument("--mode", choices=list(_MODE_NAMES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    dsn = args.database_url or os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("no database: pass --database-url or set DATABASE_URL")

    from evals.dataset import load_cases

    rows = asyncio.run(fetch_rows(dsn, args.user_email))
    candidates = build_candidates(rows, {c["prompt"] for c in load_cases()}, args.mode)
    Path(args.out).write_text(
        "# Candidate cases exported from agent_runs. Review each one, complete `fixture`/`expect`, then move it into\n"
        "# generation.yaml / editing.yaml / qa.yaml and delete `needs_review`. Not loaded by the suite.\n"
        + yaml.safe_dump(candidates, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    print(f"{len(rows)} run(s) read for that user -> {len(candidates)} new candidate(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
