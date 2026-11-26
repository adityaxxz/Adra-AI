"""A model sometimes returns a whole file JSON-escaped twice: one line of literal backslash-n / backslash-quote
text. Seen live on the eval case gen-03-blog-api, where it left app/schemas.py unparseable and the integrator
did not repair it."""
import ast
import json

import pytest

from agent import graph as G
from agent import tools as T
from agent.state import Architect, CoderOutput, File, FileUpdate, IntegrationResult, Plan, TaskPlan

# app/schemas.py exactly as the model wrote it (eval run 2026-11-23): 0 real newlines, 19 literal \n.
REAL_BROKEN_SCHEMAS = (
    r"from typing import Optional\nfrom datetime import datetime\nfrom pydantic import BaseModel\n\nclass PostCreate(BaseModel):"
    r"\n    title: str\n    content: str\n\nclass PostUpdate(BaseModel):\n    title: Optional[str] = None\n"
    r"    content: Optional[str] = None\n\nclass PostResponse(BaseModel):\n    id: int\n    title: str\n    content: str\n"
    r"    created_at: datetime\n\n    class Config:\n        orm_mode = True"
)
REAL_BROKEN_DATABASE = (
    r'import os\nfrom sqlalchemy import create_engine\n\nDATABASE_URL = os.getenv(\"DATABASE_URL\", \"sqlite:///./blog.db\")\n'
    r'engine = create_engine(DATABASE_URL)\n'
)
BACKSLASH_N = "\\n"          # the two characters, not a newline


def test_the_fixtures_really_are_one_line_of_literal_escapes():
    for text in (REAL_BROKEN_SCHEMAS, REAL_BROKEN_DATABASE):
        assert "\n" not in text.strip() and text.count(BACKSLASH_N) >= 3
    with pytest.raises(SyntaxError):
        ast.parse(REAL_BROKEN_SCHEMAS)


def test_a_double_escaped_python_file_is_decoded_into_valid_code():
    fixed = G._fix_double_escaping(REAL_BROKEN_SCHEMAS, "app/schemas.py")
    tree = ast.parse(fixed)
    assert [n.name for n in tree.body if isinstance(n, ast.ClassDef)] == ["PostCreate", "PostUpdate", "PostResponse"]
    assert fixed.startswith("from typing import Optional\nfrom datetime import datetime\n")
    assert BACKSLASH_N not in fixed


def test_escaped_quotes_are_decoded_too():
    fixed = G._fix_double_escaping(REAL_BROKEN_DATABASE, "app/database.py")
    ast.parse(fixed)
    assert 'os.getenv("DATABASE_URL", "sqlite:///./blog.db")' in fixed


def test_a_normal_multiline_file_is_left_alone():
    code = "def f():\n    return 'a\\nb\\nc\\nd'\n"
    assert code.count("\n") == 2 and code.count(BACKSLASH_N) == 3
    assert G._fix_double_escaping(code, "x.py") == code


def test_a_legitimate_one_line_python_file_with_newline_escapes_is_left_alone():
    """The tempting heuristic ('no real newlines, several \\n') would corrupt this."""
    code = 'print("a\\nb\\nc\\nd")'
    assert "\n" not in code and code.count(BACKSLASH_N) == 3
    ast.parse(code)
    assert G._fix_double_escaping(code, "hello.py") == code


def test_a_file_that_cannot_be_decoded_is_left_alone():
    broken = r'x = "unescaped " quote\ny = 1\nz = 2\nw = 3'      # not a valid JSON string body
    assert G._fix_double_escaping(broken, "x.py") == broken


def test_python_that_is_still_invalid_after_decoding_is_left_alone():
    junk = r"def f(:\n    pass\n    pass\n    pass"
    assert G._fix_double_escaping(junk, "x.py") == junk


def test_few_escapes_are_not_enough_to_trigger_a_repair_in_unchecked_file_types():
    text = r"line one\nline two"
    assert G._fix_double_escaping(text, "notes.txt") == text


def test_other_file_types_are_decoded_on_the_heuristic_alone():
    html = r'<html>\n<body>\n<h1 class=\"t\">Hi</h1>\n</body>\n</html>'
    assert G._fix_double_escaping(html, "index.html") == '<html>\n<body>\n<h1 class="t">Hi</h1>\n</body>\n</html>'


def test_json_files_are_only_decoded_when_the_result_is_valid_json():
    doubled = r'{\n  \"name\": \"blog\",\n  \"version\": \"1.0\",\n  \"private\": true\n}'
    assert json.loads(G._fix_double_escaping(doubled, "package.json"))["name"] == "blog"
    valid_one_line = '{"text": "a\\nb\\nc\\nd"}'
    assert "\n" not in valid_one_line and valid_one_line.count(BACKSLASH_N) == 3
    assert G._fix_double_escaping(valid_one_line, "data.json") == valid_one_line


# ----------------------------------------------------------- applied where the model's files are written

@pytest.fixture
def project(tmp_path):
    T.set_project_root(str(tmp_path))
    yield tmp_path
    T.set_project_root(None)


def _generation_llm(coder_content, integrator_updates):
    def respond(schema, prompt, **kw):
        if schema is Plan:
            return Plan(name="Blog", description="d", techstack="python", features=["f"], files=[File(path="app/schemas.py", purpose="p")])
        if schema is TaskPlan:
            return TaskPlan(steps=[Architect(filepath="app/schemas.py", task_description="schemas")])
        if schema is CoderOutput:
            return CoderOutput(content=coder_content)
        if schema is IntegrationResult:
            return IntegrationResult(updates=integrator_updates)
        raise AssertionError(schema)
    return respond


def test_the_coder_writes_a_repaired_file_to_disk(project, monkeypatch):
    monkeypatch.setattr(G, "structured_invoke", _generation_llm(REAL_BROKEN_SCHEMAS, []))
    G.project_generation_agent.invoke({"user_prompt": "blog", "session_id": "s"}, {"recursion_limit": 30})
    ast.parse((project / "app" / "schemas.py").read_text(encoding="utf-8"))


def test_the_integrator_can_also_return_a_double_escaped_file(project, monkeypatch):
    updates = [FileUpdate(filepath="app/schemas.py", content=REAL_BROKEN_SCHEMAS)]
    monkeypatch.setattr(G, "structured_invoke", _generation_llm("x = 1\n", updates))
    G.project_generation_agent.invoke({"user_prompt": "blog", "session_id": "s"}, {"recursion_limit": 30})
    ast.parse((project / "app" / "schemas.py").read_text(encoding="utf-8"))


# ---------------------------------------------------- quotes escaped in an otherwise normal file

HTML_BEFORE = '<html lang="en">\n<head>\n<meta charset="UTF-8">\n<title>Hi</title>\n</head>\n</html>\n'
HTML_ESCAPED = '<!-- page -->\n<html lang=\\"en\\">\n<head>\n<meta charset=\\"UTF-8\\">\n<title>Hi</title>\n</head>\n</html>\n'
HTML_FIXED = HTML_ESCAPED.replace('\\"', '"')


def test_quotes_the_model_backslash_escaped_in_an_html_file_are_unescaped():
    # Seen live: a one-line edit came back with lang=\"en\" on every line, corrupting the whole page.
    assert G._fix_escaped_quotes(HTML_ESCAPED, "index.html", HTML_BEFORE) == HTML_FIXED


def test_escaped_quotes_are_left_alone_when_they_are_legitimate():
    # valid JSON / Python whose strings really contain escaped quotes
    assert G._fix_escaped_quotes('{"a": "say \\"hi\\""}', "a.json", '{"a": 1}') == '{"a": "say \\"hi\\""}'
    py = "msg = 'say \\\"hi\\\"'\n"
    assert G._fix_escaped_quotes(py, "a.py", 'msg = "x"\n') == py
    # the file already used escaped quotes before the edit
    js = "const s = 'a \\\"b\\\"';\n"
    assert G._fix_escaped_quotes(js, "a.js", js) == js
    # some quotes are plain, so this isn't the all-escaped failure
    mixed = '<a href="x" title=\\"y\\">\n'
    assert G._fix_escaped_quotes(mixed, "a.html", HTML_BEFORE) == mixed


def test_a_new_file_needs_more_evidence_before_its_quotes_are_touched():
    assert G._fix_escaped_quotes('<a href=\\"x\\">\n', "new.html", "") == '<a href=\\"x\\">\n'
    many = '<a href=\\"1\\" title=\\"2\\">\n'
    assert G._fix_escaped_quotes(many, "new.html", "") == '<a href="1" title="2">\n'


def test_a_file_with_one_quote_left_unescaped_is_still_repaired():
    """Seen in the CI quality gate (2026-11-26, editing mode): every quote was escaped except the file's opening \"\"\", so
    decoding the text as one JSON string failed and the broken storage.py was saved as-is."""
    from pathlib import Path

    broken = (Path(__file__).parent / "samples" / "ci_double_escaped_storage.txt").read_text(encoding="utf-8")
    with pytest.raises(SyntaxError):
        ast.parse(broken)
    fixed = G._fix_double_escaping(broken, "storage.py")
    tree = ast.parse(fixed)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {"load_todos", "save_todos", "add_todo", "mark_done"} <= names, names
    assert fixed.startswith('"""Todo persistence: a single JSON file on disk."""\nimport json\n')


def test_an_escaped_backslash_inside_a_string_literal_survives_decoding():
    """Double-escaped `print("a\\nb")` must decode to code that still prints a literal backslash-n, not a newline."""
    source = 'x = 1\nprint("a\\nb")\ny = 2\nz = 3\n'
    doubled = source.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    assert "\n" not in doubled
    assert G._fix_double_escaping(doubled, "x.py") == source
