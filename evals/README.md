# Evals

A golden dataset and harness that run Adra-AI's real agent pipelines (generation, repository
editing, Q&A) and score the results. It answers "did that prompt/model/code change make the
agents better or worse?" with numbers instead of impressions.

```
evals/
  datasets/{generation,editing,qa}.yaml   the cases (hand-written + seeded; see `source`)
  fixtures/<name>/                        small repos that editing and Q&A cases run against
  evaluators/                             structural.py (no LLM) · retrieval.py · judge.py (Gemini 2.5 Flash)
  run_eval.py                             CLI harness          calibrate_judge.py   checks the judge itself
  export_seeds.py                         real prompts from agent_runs -> candidates for review
```

## Run

```bash
python -m evals.run_eval --no-judge --suite qa           # cheapest: structural + retrieval only
python -m evals.run_eval                                 # everything, with the LLM judge
python -m evals.run_eval --exec                          # also run each case's executable checks
python -m evals.run_eval --case edit-04-truncate-bug     # one case (repeatable)
python -m evals.run_eval --repeat 3 --no-judge           # run each case 3x to find flaky ones
python -m evals.run_eval --judge-model gemini-2.5-flash-lite   # a different judge model (or set EVAL_JUDGE_MODEL)
python -m evals.run_eval --min-interval 20              # pace the agent's LLM calls (Groq's free tier caps tokens/minute)
python -m evals.run_eval --judge-all                    # also judge cases that already failed a deterministic check
python -m evals.calibrate_judge --model gemini-2.5-flash-lite   # does the judge agree with labelled good/bad outputs?
```

**Provider limits are real.** Gemini's free tier allows roughly 20 requests per day *per model* (a calibration run
alone uses them all) and Groq's on-demand tier 8,000 tokens/minute for `gpt-oss-120b`. The harness re-runs a case
that dies on a rate limit (`--infra-retries`, default 2, recorded in the report), stops asking a judge whose daily
quota is gone and reports those cases as *unavailable* rather than judged, and saves the report after every case.

Needs the real keys (`GROQ_API_KEY` for the agents, `GOOGLE_API_KEY` for embeddings and the judge)
and a reachable Qdrant. Reports land in `evals/reports/` (gitignored). Every run costs real LLM
calls and takes minutes (the agents are throttled to ~2.5 s per call).

**`--exec` runs LLM-generated code on this machine.** It uses a stripped environment (no API keys),
a temp directory and a timeout, but it is *not* a sandbox. Leave it off if you don't trust the model's output.

## What gets scored

| Layer | Checks | Needs an LLM |
|---|---|---|
| Structural | files exist · python/json/js syntax · **project-local imports resolve** (names, not just modules) · html `<script>`/`<link>` targets exist · **js element ids exist in the html** · no TODO/NotImplemented stubs · required content/definitions | no |
| Editing | the right files changed · **files that shouldn't change are byte-identical** · existing functions survive · nothing deleted | no |
| Executable (`--exec`) | the case's own assertions run against the output | no |
| Retrieval (Q&A) | hit@k, recall, MRR of the chunks the agent saw vs the file that holds the answer (advisory) | no |
| Judge | correctness / completeness / instruction-following (code), faithfulness / correctness / relevance + hallucination (answers) — each 1-5, all must be ≥ 4 | Gemini 2.5 Flash |

A case **passes** when no required check fails. Pipeline crashes are `error`s and count *against* the pass rate.
Structural and judge pass rates are reported separately because the judge is the noisier signal.

## Adding a case

Add it to the right YAML file. `source` must say where it came from: `hand-written`, `seeded-verbatim`
(a prompt a real user typed) or `seeded-inferred` (reconstructed from artifacts, *not* verbatim).
Editing cases need a `fixture`; Q&A cases need a `fixture`, a `reference` answer and `expect.sources`.
Then run `pytest tests/test_eval_dataset.py`, which enforces that:

- every editing case **fails on the untouched fixture** (doing nothing can't pass);
- every `solution` passes its own case, executable checks included (the checks are satisfiable);
- every case with `exec` checks has such a solution (an exec check nobody has seen pass is a liability);
- every Q&A `reference` satisfies its own deterministic expectations;
- fixtures are themselves healthy, and unknown `expect` keys (typos) are rejected.

## Seeding from real prompts

```bash
python -m evals.export_seeds --user-email you@example.com
```

Reads **only that user's** runs from `agent_runs` (an explicit email is required - prompts are user
content) and writes `evals/datasets/seed_candidates.yaml` (gitignored, never loaded by the suite).
Review each candidate, give it a fixture/expectations, and move it into a dataset file.

## Caveats

- Agents run at temperature 0 but are still non-deterministic; use `--repeat` before trusting a small difference.
- Fixtures are small. A passing score means "handles these cases", not "handles your codebase".
- The judge is validated by `calibrate_judge` (and `pytest -m live tests/test_eval_judge.py`), not assumed correct.
