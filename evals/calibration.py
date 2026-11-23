"""Known-good and known-bad outputs with a labelled verdict, used to check that the LLM judge
agrees with ground truth ("an eval of the eval"). Each bad item fails in exactly one way."""
from evals.dataset import fixture_files, load_cases

_CASES = {c["id"]: c for c in load_cases()}


def _context(fixture: str, *paths: str) -> str:
    files = fixture_files(fixture)
    return "\n\n".join(f"FILE: {p}\n\n{files[p]}" for p in paths)


def _edit(case_id: str, **override_files: str) -> dict:
    case = _CASES[case_id]
    before = fixture_files(case["fixture"])
    after = {**before, **case["solution"], **override_files}
    return {"case": case, "before": before, "after": after}


def _gen(case_id: str, **override_files: str) -> dict:
    case = _CASES[case_id]
    return {"case": case, "before": None, "after": {**case["solution"], **override_files}}


def _qa(case_id: str, answer: str) -> dict:
    case = _CASES[case_id]
    ctx = {"qa-01-todo-storage": ("todo_api", ["storage.py"]), "qa-03-todo-auth-unanswerable": ("todo_api", ["main.py", "README.md"]),
           "qa-04-todo-missing-id": ("todo_api", ["main.py", "storage.py"]), "qa-05-todo-get-before-create": ("todo_api", ["storage.py", "main.py"]),
           "qa-11-counter-about-short": ("counter_site", ["index.html", "app.js"])}[case_id]
    return {"case": case, "answer": answer, "context": _context(ctx[0], *ctx[1])}


_LONG = (
    "This project is a small web application that implements a click counter. When you open the page you see a heading "
    "called Click Counter, a line that shows the current count, and a button labelled Increment. Each time the user "
    "clicks the button the JavaScript in app.js increases a variable by one, writes the new value to the browser's "
    "localStorage so that it survives a reload, and then re-renders the number inside the span with the id count. The "
    "styling lives in style.css and keeps the layout centred with a readable system font and a simple button. Because "
    "everything runs in the browser there is no backend, no database and no build step; you can just open index.html "
    "directly. It is a very small example that demonstrates DOM manipulation, event listeners and local persistence."
)

_BAD_TRUNCATE = fixture_files("text_utils")["strings.py"].replace("return text[:length] + suffix", "return text[:length]")
_SCOPE_CREEP_STRINGS = _CASES["edit-04-truncate-bug"]["solution"]["strings.py"] \
    .replace("def slugify", "def make_slug").replace("\n\ndef word_count(text: str) -> int:", "\n\ndef _unused(text: str) -> int:")

ITEMS = [
    # ---- question answering
    {"id": "qa-faithful", "kind": "answer", "expect": "good", **_qa("qa-01-todo-storage",
     "Todos are persisted in a local JSON file, todos.json (the DATA_FILE constant in storage.py), written with json.dump and read back with json.load.")},
    {"id": "qa-invented-database", "kind": "answer", "expect": "bad", **_qa("qa-01-todo-storage",
     "Todos are stored in a SQLite database through SQLAlchemy models defined in db.py, with a todos table.")},
    {"id": "qa-honest-no-auth", "kind": "answer", "expect": "good", **_qa("qa-03-todo-auth-unanswerable",
     "The code does not implement any authentication. The README says there is none, so every endpoint is open to any client.")},
    {"id": "qa-invented-jwt", "kind": "answer", "expect": "bad", **_qa("qa-03-todo-auth-unanswerable",
     "The API uses JWT bearer tokens: clients log in at /login and then send the token in the Authorization header.")},
    {"id": "qa-extra-invented-detail", "kind": "answer", "expect": "bad", **_qa("qa-04-todo-missing-id",
     "mark_done returns None for an unknown id, so the route raises a 404 'Todo not found', and it also writes the failed lookup to an audit log table.")},
    {"id": "qa-multifile-correct", "kind": "answer", "expect": "good", **_qa("qa-05-todo-get-before-create",
     "load_todos opens todos.json without checking that it exists, so the first GET /todos on a fresh install raises FileNotFoundError, which nothing catches - the request fails with a 500.")},
    {"id": "qa-wrong-conclusion", "kind": "answer", "expect": "bad", **_qa("qa-05-todo-get-before-create",
     "It returns an empty list, because load_todos falls back to [] when todos.json does not exist yet.")},
    {"id": "qa-short-respected", "kind": "answer", "expect": "good", **_qa("qa-11-counter-about-short",
     "A tiny click-counter web page: a button increments a count, which is saved in localStorage.")},
    {"id": "qa-ignores-brevity", "kind": "answer", "expect": "bad", **_qa("qa-11-counter-about-short", _LONG)},
    # ---- editing
    {"id": "edit-correct-fix", "kind": "code", "expect": "good", **_edit("edit-04-truncate-bug")},
    {"id": "edit-wrong-fix", "kind": "code", "expect": "bad", **_edit("edit-04-truncate-bug", **{"strings.py": _BAD_TRUNCATE})},
    {"id": "edit-scope-creep", "kind": "code", "expect": "bad", **_edit("edit-04-truncate-bug", **{"strings.py": _SCOPE_CREEP_STRINGS})},
    {"id": "edit-median-correct", "kind": "code", "expect": "good", **_edit("edit-06-median")},
    {"id": "edit-median-unsorted", "kind": "code", "expect": "bad", **_edit("edit-06-median", **{"mathx.py": _CASES["edit-06-median"]["solution"]["mathx.py"].replace(
        "ordered = sorted(values)", "ordered = values")})},
    {"id": "edit-reset-correct", "kind": "code", "expect": "good", **_edit("edit-07-counter-reset")},
    {"id": "edit-reset-not-wired", "kind": "code", "expect": "bad", **_edit("edit-07-counter-reset", **{"app.js": fixture_files("counter_site")["app.js"]})},
    # ---- generation
    {"id": "gen-bank-correct", "kind": "code", "expect": "good", **_gen("gen-05-bank-account")},
    {"id": "gen-bank-allows-overdraft", "kind": "code", "expect": "bad", **_gen("gen-05-bank-account", **{"bank.py": _CASES["gen-05-bank-account"]["solution"]["bank.py"].replace(
        "        if amount > self._balance:\n            raise ValueError(\"insufficient funds\")\n", "")})},
    {"id": "gen-bank-stubbed", "kind": "code", "expect": "bad", **_gen("gen-05-bank-account", **{"bank.py": (
        "class BankAccount:\n    def __init__(self):\n        self.balance = 0\n\n    def deposit(self, amount):\n        pass\n\n    def withdraw(self, amount):\n        pass\n")})},
    {"id": "gen-csv-wrong-type", "kind": "code", "expect": "bad", **_gen("gen-07-csv-to-json", **{"csv2json.py": _CASES["gen-07-csv-to-json"]["solution"]["csv2json.py"].replace(
        'int(r["score"])', 'r["score"]')})},
]


def run_calibration(judge, on_row=None) -> dict:
    """Judge every item; return per-item results and the agreement rate with the labels.
    `on_row(row)` is called as each item completes, so progress survives a killed run."""
    rows = []
    for it in ITEMS:
        if it["kind"] == "answer":
            o = judge.judge_answer(it["case"], it["answer"], it["context"])
        else:
            o = judge.judge_code(it["case"], it["after"], it["before"])
        rows.append({"id": it["id"], "expect": it["expect"], "passed": o.passed, "agrees": o.passed is not None and (o.passed == (it["expect"] == "good")),
                     "score": o.score, "detail": o.detail})
        if on_row:
            on_row(rows[-1])
    judged = [r for r in rows if r["passed"] is not None]
    return {"rows": rows, "agreement": sum(r["agrees"] for r in judged) / len(judged) if judged else 0.0, "judged": len(judged), "total": len(rows)}
