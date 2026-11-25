"""Each structural evaluator against a broken input it must catch and a good one it must not flag."""
import shutil

import pytest

from evals.evaluators import structural as S
from evals.evaluators.retrieval import retrieval_metrics, retrieval_outcome


# ----------------------------------------------------------------- syntax / presence

def test_files_exist_uses_glob_patterns_across_directories():
    files = {"src/app.py": "", "web/index.html": "", "package.json": "{}"}
    assert S.files_exist(files, ["*.py", "*.html", "package.json"]).passed
    assert not S.files_exist(files, ["*.css"]).passed


def test_python_parses_reports_the_broken_file_and_line():
    o = S.python_parses({"a.py": "x = 1\n", "b.py": "def f(:\n    pass\n"})
    assert o.passed is False and "b.py:1" in o.detail
    assert S.python_parses({"a.py": "x = 1\n"}).passed
    assert S.python_parses({"a.txt": "hi"}).passed is None          # nothing to check


def test_json_valid():
    assert S.json_valid({"package.json": '{"a": 1}'}).passed
    assert S.json_valid({"package.json": '{"a": 1,}'}).passed is False
    assert S.json_valid({"a.py": ""}).passed is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_parses_catches_syntax_errors_but_not_jsx():
    assert S.js_parses({"a.js": "const x = 1;\nfunction f() { return x; }\n"}).passed
    assert S.js_parses({"a.js": "function f( { return 1; }"}).passed is False
    jsx = "import React from 'react';\nexport default function App() { return <div>hi</div>; }\n"
    assert S.js_parses({"App.js": jsx}).passed is None, "valid JSX must not be reported as a syntax error"


# -------------------------------------------------------------------- python imports

def test_import_of_a_name_the_module_does_not_define_is_caught():
    """The classic cross-file bug: caller and callee disagree about a name."""
    files = {"calc.py": "def add(a, b):\n    return a + b\n", "app.py": "from calc import add, multiply\n"}
    o = S.imports_resolve(files)
    assert o.passed is False and "multiply" in o.detail and "calc.py" in o.detail


def test_import_of_a_missing_local_package_member_is_caught():
    files = {"pkg/__init__.py": "", "pkg/a.py": "X = 1\n", "main.py": "from pkg import b\nimport pkg.c\n"}
    o = S.imports_resolve(files)
    assert o.passed is False and "'b'" in o.detail and "pkg.c" in o.detail


def test_valid_local_imports_are_accepted_in_every_form():
    files = {
        "pkg/__init__.py": "",
        "pkg/models.py": "class User: ...\nLIMIT = 3\n",
        "pkg/service.py": "from .models import User, LIMIT\nfrom . import models\nimport pkg.models\nimport os, json\nfrom fastapi import FastAPI\n",
        "main.py": "from pkg.service import User\nfrom pkg import models, service\n",
    }
    assert S.imports_resolve(files).passed


def test_names_bound_by_assignment_import_try_and_if_count_as_defined():
    files = {"cfg.py": "import os\ntry:\n    from x import Y\nexcept ImportError:\n    Y = None\nif os.name:\n    DEBUG = True\n",
             "use.py": "from cfg import os, Y, DEBUG\n"}
    assert S.imports_resolve(files).passed


def test_star_imports_are_not_flagged():
    files = {"a.py": "from b import *\n", "b.py": "X = 1\n", "c.py": "from a import X\n"}
    assert S.imports_resolve(files).passed


def test_declared_dependencies_flags_an_undeclared_third_party_import():
    files = {"requirements.txt": "fastapi==0.110\nuvicorn\n", "app.py": "import os\nimport requests\nfrom fastapi import FastAPI\nimport yaml\n"}
    o = S.declared_dependencies(files)
    assert o.passed is False and "requests" in o.detail and "yaml" in o.detail


def test_declared_dependencies_accepts_aliases_extras_and_local_modules():
    files = {"requirements.txt": "PyYAML>=6\nSQLAlchemy[asyncio]==2.0\npython-dotenv\n", "util.py": "X = 1\n",
             "app.py": "import yaml\nfrom sqlalchemy import create_engine\nfrom dotenv import load_dotenv\nimport util\nimport json\n"}
    assert S.declared_dependencies(files).passed


def test_declared_dependencies_is_skipped_without_a_requirements_file():
    assert S.declared_dependencies({"a.py": "import requests"}).passed is None


# ------------------------------------------------------------------------- web files

def test_html_refs_must_exist():
    page = '<link rel="stylesheet" href="style.css"><script src="app.js"></script><script src="https://cdn.x/y.js"></script><a href="other.html">x</a>'
    assert S.html_refs_resolve({"index.html": page, "style.css": "", "app.js": ""}).passed
    o = S.html_refs_resolve({"index.html": page, "app.js": ""})
    assert o.passed is False and "style.css" in o.detail


def test_html_refs_resolve_relative_to_the_page_directory():
    assert S.html_refs_resolve({"web/index.html": '<script src="js/app.js"></script>', "web/js/app.js": ""}).passed
    assert S.html_refs_resolve({"web/index.html": '<script src="js/app.js"></script>', "js/app.js": ""}).passed is False


def test_js_looking_up_an_id_the_html_never_defines_is_caught():
    html = '<button id="add">+</button><ul id="list"></ul>'
    bad = "document.getElementById('add'); document.querySelector('#clear-all'); document.getElementById('list');"
    o = S.dom_ids_resolve({"index.html": html, "app.js": bad})
    assert o.passed is False and "clear-all" in o.detail and "add" not in o.detail.replace("clear-all", "")
    assert S.dom_ids_resolve({"index.html": html, "app.js": "document.getElementById('add');"}).passed


def test_ids_created_by_the_script_itself_are_not_flagged():
    js = "const el = document.createElement('div'); el.id = 'toast'; document.body.append(el);\ndocument.getElementById('toast');"
    assert S.dom_ids_resolve({"index.html": "<body></body>", "app.js": js}).passed


# --------------------------------------------------------------- content heuristics

def test_placeholders_are_flagged_in_code_but_not_in_legitimate_text():
    assert S.no_placeholders({"a.py": "def f():\n    # TODO: implement\n    pass\n"}).passed is False
    assert S.no_placeholders({"a.py": "def f():\n    raise NotImplementedError\n"}).passed is False
    assert S.no_placeholders({"a.js": "// FIXME later\n"}).passed is False
    # an app *called* TODO, an input placeholder attribute, and prose in a README are all fine
    ok_files = {"index.html": '<title>TODO List</title><input placeholder="Add a todo...">', "README.md": "TODO: write docs",
                "a.py": "todo_items = []  # the todo list\n"}
    assert S.no_placeholders(ok_files).passed


def test_ordinary_todo_app_code_is_not_mistaken_for_a_placeholder():
    """gen-01 (a to-do web app) failed live on `styles.css:15`: '#' was treated as a comment opener in every
    language, so a CSS id selector like #todo-list matched case-insensitively."""
    for name, text in {
        "styles.css": "body { margin: 0; }\n#todo-list {\n  padding: 0;\n}\n#todo-input:focus { outline: none; }\n",
        "a.css": "/* Todo list styles */\n.todo-item { color: #333; }\n",
        "index.html": '<a href="#todo-section">jump</a><section id="todo-section"></section>',
        "app.js": "const el = document.querySelector('#todo-list');\n// Todo items are rendered here\n",
        "a.py": "# Todo items live in this list\nitems = []\n",
        "upper.css": "#TODO-LIST { margin: 0; }\n",                       # '#' only opens a comment in Python
        "upper.html": '<a href="#TODO">jump</a><section id="TODO"></section>',
    }.items():
        assert S.no_placeholders({name: text}).passed, name


def test_real_placeholders_are_still_caught_in_every_comment_style():
    for name, text in {
        "a.py": "# TODO: finish\n", "a.py ": "#TODO\n", "b.py": "# todo: finish\n", "a.js": "// TODO implement\n",
        "a.css": "/* FIXME */\n", "a.html": "<!-- TODO: add form -->\n", "c.js": "/* XXX hack */\n", "d.js": "// fixme: later\n",
        "e.py": "def f():\n    raise NotImplementedError\n", "f.js": "function f() { /* your code here */ }\n",
    }.items():
        assert S.no_placeholders({name.strip(): text}).passed is False, name


def test_contains_rules():
    files = {"app.js": "document.addEventListener('click', f)", "index.html": "<BUTTON>Go</BUTTON>"}
    assert S.contains(files, [{"file": "*.js", "any": ["addEventListener", "onclick"]}, {"file": "*.html", "any": ["<button"]}]).passed
    assert S.contains(files, [{"file": "*.js", "all": ["click", "missing"]}]).passed is False
    assert S.contains(files, [{"file": "*.css", "any": ["x"]}]).passed is False          # no such file
    assert S.contains(files, [{"regex": r"addEventListener\('\w+'"}]).passed
    assert S.contains(files, [{"any": ["nowhere"]}]).passed is False


def test_not_contains():
    assert S.not_contains({"a.py": "import sqlite3"}, [{"terms": ["postgres"]}]).passed
    assert S.not_contains({"a.py": "import sqlite3"}, [{"terms": ["SQLite3"]}]).passed is False


def test_defines_for_python_and_javascript():
    py = {"m.py": "class Bank:\n    def deposit(self): ...\n\ndef delete_post(): ...\n"}
    assert S.defines(py, [{"file": "m.py", "names": ["Bank", "deposit"]}]).passed
    assert S.defines(py, [{"file": "m.py", "names": ["withdraw"]}]).passed is False
    assert S.defines(py, [{"files": ["*.py"], "regex": "delete|remove"}]).passed
    js = {"a.js": "function render() {}\nconst save = () => {};\nclass App {}\n"}
    assert S.defines(js, [{"file": "a.js", "names": ["render", "save", "App"]}]).passed


# ------------------------------------------------------------ editing: before / after

def test_modified_and_unmodified():
    before = {"a.py": "x = 1\n", "b.py": "y = 2\n"}
    after = {"a.py": "x = 2\n", "b.py": "y = 2\n"}
    assert S.modified(before, after, ["a.py"]).passed
    assert S.modified(before, after, ["b.py"]).passed is False
    assert S.unmodified(before, after, ["b.py"]).passed
    o = S.unmodified(before, after, ["*.py"])
    assert o.passed is False and "a.py" in o.detail


def test_line_ending_changes_alone_do_not_count_as_a_modification():
    assert S.unmodified({"a.py": "x = 1\ny = 2\n"}, {"a.py": "x = 1\r\ny = 2\r\n"}, ["a.py"]).passed


def test_a_new_file_counts_as_modified_and_deleting_files_is_caught():
    assert S.modified({"a.py": "x"}, {"a.py": "x", "new.py": "y"}, ["new.py"]).passed
    assert S.no_files_deleted({"a.py": "x", "b.py": "y"}, {"a.py": "x"}).passed is False
    assert S.no_files_deleted({"a.py": "x", "b.py": "y"}, {"a.py": "x"}, allow=["b.py"]).passed


def test_preserved_symbols_catches_an_edit_that_drops_existing_functions():
    before = {"s.py": "def slugify(): ...\ndef truncate(): ...\n"}
    after = {"s.py": "def slugify(): ...\ndef title_case(): ...\n"}
    o = S.preserved_symbols(before, after, [{"file": "s.py", "names": ["slugify", "truncate"]}])
    assert o.passed is False and "s.py:truncate" in o.detail
    assert S.preserved_symbols(before, before, [{"file": "s.py", "names": ["slugify", "truncate"]}]).passed


# -------------------------------------------------------------------------- answers

def test_answer_contains_needs_every_group():
    assert S.answer_contains("Todos live in todos.json as JSON.", [["json"], ["todos.json", "DATA_FILE"]]).passed
    assert S.answer_contains("Todos live in a JSON file.", [["json"], ["todos.json"]]).passed is False


def test_answer_not_contains_and_max_words():
    assert S.answer_not_contains("It uses a JSON file.", ["postgres"]).passed
    assert S.answer_not_contains("It uses Postgres.", ["postgres"]).passed is False
    assert S.answer_max_words("a b c", 3).passed and S.answer_max_words("a b c d", 3).passed is False


@pytest.mark.parametrize("text,honest", [
    ("The provided code does not show any authentication.", True),
    ("No. There is no authentication in this API.", True),
    ("Nothing in the code handles that.", True),
    ("I can't find anything about that in the context.", True),
    ("It authenticates users with JWT bearer tokens.", False),
    ("Yes, it normalises accents with unicodedata.", False),
    ("Nobody asked, but it supports OAuth2.", False),
])
def test_admits_unknown_accepts_honest_refusals_and_rejects_inventions(text, honest):
    assert S.admits_unknown(text).passed is honest


# ----------------------------------------------------------------- executable checks

def test_exec_checks_pass_fail_and_time_out():
    files = {"m.py": "def add(a, b):\n    return a + b\n"}
    good, bad, hang, out = S.run_exec_checks(files, [
        {"name": "good", "snippet": "from m import add; assert add(1, 2) == 3"},
        {"name": "bad", "snippet": "from m import add; assert add(1, 2) == 4"},
        {"name": "hang", "snippet": "import time; time.sleep(30)", "timeout": 1},
        {"name": "out", "cmd": ["python", "-c", "print('hello there')"], "stdout_contains": ["HELLO", "missing"]},
    ])
    assert good.passed is True
    assert bad.passed is False and "AssertionError" in bad.detail
    assert hang.passed is False and "timed out" in hang.detail
    assert out.passed is False and "missing" in out.detail


def test_exec_checks_run_in_a_scratch_dir_with_setup_files_and_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-secret")
    (o,) = S.run_exec_checks({"m.py": "X = 1\n"}, [{
        "name": "env and files",
        "setup_files": {"data.txt": "42"},
        "snippet": "import os\nassert open('data.txt').read() == '42'\nassert 'GROQ_API_KEY' not in os.environ and 'GOOGLE_API_KEY' not in os.environ",
    }])
    assert o.passed is True, o.detail


# ----------------------------------------------------------------------- retrieval

def test_retrieval_metrics():
    m = retrieval_metrics(["a.py", "b.py", "a.py", "c.py", "d.py"], ["b.py", "z.py"], k=5)
    assert m["hit"] is True and m["mrr"] == 0.5
    assert m["recall"] == 0.5                 # b.py found, z.py never surfaced
    assert m["precision"] == pytest.approx(1 / 5)
    miss = retrieval_metrics(["a.py", "c.py"], ["b.py"], k=5)
    assert miss["hit"] is False and miss["mrr"] == 0.0


def test_retrieval_only_counts_the_top_k_and_normalises_paths():
    assert retrieval_metrics(["x.py", "y.py", "src\\target.py"], ["src/target.py"], k=2)["hit"] is False
    assert retrieval_metrics(["x.py", "y.py", "src\\target.py"], ["src/target.py"], k=3)["hit"] is True
    o = retrieval_outcome(["a.py"], ["b.py"])
    assert o.passed is False and o.required is False and o.kind == "retrieval"     # advisory: reported, never fails a case alone


def test_an_exec_check_can_report_that_it_could_not_run_here():
    """A project that needs a package the eval machine lacks is not broken; the check says so instead of failing."""
    (o,) = S.run_exec_checks({}, [{"name": "needs sqlmodel", "snippet": "print('SKIP: needs sqlmodel')", "stdout_contains": ["ok"]}])
    assert o.passed is None and "sqlmodel" in o.detail
    (bad,) = S.run_exec_checks({}, [{"name": "crashes", "snippet": "print('SKIP: x'); raise SystemExit(3)"}])
    assert bad.passed is False, "a non-zero exit is a failure even if it printed SKIP"


def test_a_failed_exec_check_reports_the_exception_not_a_trailing_note():
    """SQLAlchemy ends its errors with "(Background on this error at: <url>)", which used to be all the report showed."""
    snippet = ("import sys\n"
               "sys.stderr.write('Traceback (most recent call last):\\n  File x\\n"
               "sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: posts\\n"
               "[SQL: INSERT INTO posts]\\n(Background on this error at: https://sqlalche.me/e/20/e3q8)\\n')\n"
               "raise SystemExit(1)\n")
    (o,) = S.run_exec_checks({}, [{"name": "api", "snippet": snippet}])
    assert o.passed is False and "no such table: posts" in o.detail, o.detail
