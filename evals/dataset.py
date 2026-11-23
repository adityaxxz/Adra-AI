"""Load and validate the golden dataset (evals/datasets/*.yaml)."""
from pathlib import Path

import yaml

from evals.evaluators.evaluate import EXPECT_KEYS, JUDGE_KEYS

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "datasets"
FIXTURES = ROOT / "fixtures"
MODES = ("generation", "editing", "question_answering")
SOURCES = ("hand-written", "seeded-verbatim", "seeded-inferred", "seeded-export")
SUITE_FILES = {"generation": "generation.yaml", "editing": "editing.yaml", "question_answering": "qa.yaml"}


def load_cases(mode: str | None = None) -> list[dict]:
    modes = [mode] if mode else list(MODES)
    cases = []
    for m in modes:
        cases.extend(yaml.safe_load((DATASETS / SUITE_FILES[m]).read_text(encoding="utf-8")) or [])
    return cases


def read_tree(root: Path) -> dict:
    """A directory as {posix relative path: text}, skipping binary files and VCS/cache dirs."""
    skip = {".git", "__pycache__", "node_modules", ".pytest_cache"}
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and not (set(p.relative_to(root).parts) & skip):
            try:
                out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
    return out


def fixture_files(name: str) -> dict:
    return read_tree(FIXTURES / name)


def problems(case: dict) -> list[str]:
    """Static problems with one case (an empty list means it is well-formed)."""
    errs = []
    cid = case.get("id", "<no id>")
    for key in ("id", "mode", "source", "prompt"):
        if not case.get(key):
            errs.append(f"{cid}: missing '{key}'")
    mode = case.get("mode")
    if mode not in MODES:
        return errs + [f"{cid}: unknown mode {mode!r}"]
    if case.get("source") not in SOURCES:
        errs.append(f"{cid}: unknown source {case.get('source')!r}")
    unknown = set(case.get("expect", {})) - EXPECT_KEYS[mode]
    if unknown:
        errs.append(f"{cid}: unknown expect keys {sorted(unknown)} for mode {mode}")
    if set(case.get("judge", {})) - JUDGE_KEYS:
        errs.append(f"{cid}: unknown judge keys {sorted(set(case['judge']) - JUDGE_KEYS)}")
    if mode in ("editing", "question_answering"):
        if not case.get("fixture") or not (FIXTURES / case["fixture"]).is_dir():
            errs.append(f"{cid}: fixture {case.get('fixture')!r} does not exist")
    if mode == "question_answering" and not case.get("reference"):
        errs.append(f"{cid}: question_answering cases need a 'reference' answer")
    if mode == "question_answering" and not case.get("expect", {}).get("sources"):
        errs.append(f"{cid}: question_answering cases need expect.sources (for the retrieval metrics)")
    return errs
