"""Phase 4 "Version prompts": a prompt must not change without its version number changing.

Each prompt is rendered with fixed inputs (covering its branches, e.g. the Coder for a new file and for an existing one)
and fingerprinted. The fingerprints are saved in tests/samples/prompt_fingerprints.json next to the version they belong
to. Change a prompt and keep its version -> this fails. After bumping the version, refresh the file with:

    python tests/test_prompt_versions.py

Only what is sent to the model counts: comments or code outside the prompt text don't change a fingerprint.
"""
import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINGERPRINTS = ROOT / "tests" / "samples" / "prompt_fingerprints.json"
REFRESH = "python tests/test_prompt_versions.py"

if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))

from agent import prompts as P  # noqa: E402


def _renders() -> dict:
    return {
        "planner": [P.planner_prompt("USER")],
        "edit_planner": [P.edit_planner_prompt("USER", "RETRIEVED", "FILES")],
        "architect": [P.architect_prompt("PLAN")],
        "coder": [P.coder_prompt("f.py", "TASK", "", "SIBLINGS", "SUMMARY"),
                  P.coder_prompt("f.py", "TASK", "EXISTING", "SIBLINGS", "SUMMARY", "REPO")],
        "integrator": [P.integrator_prompt("FILES", "SUMMARY"),
                       P.integrator_prompt("FILES", "SUMMARY", "REFERENCE"),
                       P.integrator_prompt("FILES", "SUMMARY", new_project=True)],
        "explainer": [P.explainer_prompt("QUESTION", "REPO")],
    }


def current_fingerprints() -> dict:
    return {name: {"version": P.PROMPT_VERSIONS[name],
                   "sha": hashlib.sha256("\x00".join(texts).encode("utf-8")).hexdigest()[:16]}
            for name, texts in sorted(_renders().items())}


def test_every_prompt_builder_is_versioned_and_fingerprinted():
    builders = {name[:-len("_prompt")] for name, fn in inspect.getmembers(P, inspect.isfunction)
                if name.endswith("_prompt") and fn.__module__ == P.__name__}
    assert builders == set(P.PROMPT_VERSIONS) == set(_renders()), \
        "a prompt builder was added or removed: update PROMPT_VERSIONS and _renders() in this test"


def test_mode_prompts_name_only_versioned_prompts():
    for mode, names in P.MODE_PROMPTS.items():
        assert set(names) <= set(P.PROMPT_VERSIONS), mode
    assert P.prompt_versions_for("question_answering") == {"explainer": P.PROMPT_VERSIONS["explainer"]}
    assert set(P.prompt_versions_for("editing")) == {"edit_planner", "coder", "integrator"}
    assert P.prompt_versions_for("unknown") == {}


def test_no_prompt_changed_without_a_version_bump():
    saved = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    problems = []
    for name, now in current_fingerprints().items():
        old = saved.get(name)
        if old == now:
            continue
        if old and old["sha"] != now["sha"] and old["version"] == now["version"]:
            problems.append(f"'{name}' prompt changed but is still v{now['version']}: bump PROMPT_VERSIONS['{name}'] "
                            f"in agent/prompts.py, then run `{REFRESH}`")
        elif old and old["version"] > now["version"]:
            problems.append(f"'{name}' version went down (v{old['version']} -> v{now['version']}); versions only go up")
        else:
            problems.append(f"'{name}' fingerprint file is out of date: run `{REFRESH}`")
    assert not problems, "\n".join(problems)


def test_the_check_catches_a_changed_prompt(monkeypatch):
    """The guard itself works: altering shared prompt text (not just a builder) changes the fingerprint."""
    before = current_fingerprints()
    monkeypatch.setattr(P, "UNTRUSTED_NOTICE", P.UNTRUSTED_NOTICE + " extra")
    after = current_fingerprints()
    assert {n for n in before if before[n]["sha"] != after[n]["sha"]} == {"edit_planner", "coder", "integrator", "explainer"}


if __name__ == "__main__":
    FINGERPRINTS.write_text(json.dumps(current_fingerprints(), indent=2) + "\n", encoding="utf-8")
    print(f"refreshed {FINGERPRINTS.relative_to(ROOT)}")
