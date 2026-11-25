"""Deterministic checks on generated / edited projects. No LLM, no network.

A project is a `dict[str, str]` of posix-style relative path -> text content.
Every check returns an `Outcome`; `passed=None` means "could not be evaluated"
(for example `node` is not installed), which never fails a case.
"""
import ast
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Optional

from evals.evaluators.outcome import Outcome, fail, ok, skipped

CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css"}
_EXTERNAL_REF = re.compile(r"^([a-z][a-z0-9+.-]*:|//|#)", re.I)


def _match(files: dict, pattern: str) -> list[str]:
    return sorted(p for p in files if fnmatch.fnmatch(p, pattern))


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


# ------------------------------------------------------------------- presence / syntax

def files_exist(files: dict, patterns: list[str]) -> Outcome:
    missing = [p for p in patterns if not _match(files, p)]
    if missing:
        return fail("files_exist", f"no file matches: {missing}; have: {sorted(files)}")
    return ok("files_exist", f"{len(patterns)} pattern(s) matched")


def python_parses(files: dict) -> Outcome:
    py = [p for p in files if p.endswith(".py")]
    if not py:
        return skipped("python_parses", "no .py files")
    errors = []
    for p in py:
        try:
            ast.parse(files[p])
        except SyntaxError as e:
            errors.append(f"{p}:{e.lineno}: {e.msg}")
    return fail("python_parses", "; ".join(errors)) if errors else ok("python_parses", f"{len(py)} file(s)")


def json_valid(files: dict) -> Outcome:
    js = [p for p in files if p.endswith(".json")]
    if not js:
        return skipped("json_valid", "no .json files")
    errors = []
    for p in js:
        try:
            json.loads(files[p])
        except ValueError as e:
            errors.append(f"{p}: {e}")
    return fail("json_valid", "; ".join(errors)) if errors else ok("json_valid", f"{len(js)} file(s)")


def js_parses(files: dict) -> Outcome:
    """Syntax-check .js files with `node --check`. Skipped when node isn't installed."""
    # `node --check` rejects JSX, which React projects legitimately keep in .js files.
    jsx = re.compile(r"""from\s+['"]react['"]|\bReact\.|</?[A-Z][A-Za-z0-9]*[\s/>]""")
    js = [p for p in files if p.endswith(".js") and not jsx.search(files[p])]
    if not js:
        return skipped("js_parses", "no plain .js files")
    node = shutil.which("node")
    if not node:
        return skipped("js_parses", "node not installed")
    errors = []
    with tempfile.TemporaryDirectory() as td:
        for p in js:
            f = Path(td) / "check.js"
            f.write_text(files[p], encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                first = next((ln for ln in r.stderr.splitlines() if "Error" in ln), r.stderr.strip()[:120])
                errors.append(f"{p}: {first}")
    return fail("js_parses", "; ".join(errors)) if errors else ok("js_parses", f"{len(js)} file(s)")


# --------------------------------------------------------------------- python imports

def _module_index(files: dict) -> dict:
    """dotted module name -> file path, for every .py file in the project."""
    mods = {}
    for path in files:
        if not path.endswith(".py"):
            continue
        parts = list(PurePosixPath(path).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            mods[".".join(parts)] = path
    return mods


def _defined_names(tree: ast.Module) -> Optional[set]:
    """Names a module defines at its top level, or None if it star-imports (unknowable)."""
    names: set = set()

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    names.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == "*":
                        names.add("*")
                    names.add(a.asname or a.name)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for attr in ("body", "orelse", "finalbody"):
                    visit(getattr(node, attr, []) or [])
                for h in getattr(node, "handlers", []) or []:
                    visit(h.body)

    visit(tree.body)
    return None if "*" in names else names


def imports_resolve(files: dict) -> Outcome:
    """Every import of a *project-local* module must resolve, and every name imported
    from one must actually be defined there. Stdlib and third-party imports are ignored
    (see `declared_dependencies` for those)."""
    mods = _module_index(files)
    if not mods:
        return skipped("imports_resolve", "no .py files")
    roots = {m.split(".")[0] for m in mods}
    trees, errors = {}, []
    for dotted, path in mods.items():
        try:
            trees[dotted] = ast.parse(files[path])
        except SyntaxError:
            return fail("imports_resolve", f"cannot check: {path} does not parse")

    def is_package_prefix(name):
        return any(m.startswith(name + ".") for m in mods)

    def check_from(path, module, names, lineno):
        if module in mods:
            defined = _defined_names(trees[module])
            for n in names:
                if n == "*" or defined is None:
                    continue
                if n not in defined and f"{module}.{n}" not in mods:
                    errors.append(f"{path}:{lineno}: '{n}' is not defined in {mods[module]}")
        elif is_package_prefix(module):
            for n in names:
                if n != "*" and f"{module}.{n}" not in mods:
                    errors.append(f"{path}:{lineno}: package '{module}' has no module '{n}'")
        else:
            errors.append(f"{path}:{lineno}: module '{module}' does not exist in the project")

    for dotted, path in mods.items():
        pkg = dotted.split(".")[:-1] if not path.endswith("__init__.py") else dotted.split(".")
        for node in ast.walk(trees[dotted]):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in roots and a.name not in mods and not is_package_prefix(a.name):
                        errors.append(f"{path}:{node.lineno}: module '{a.name}' does not exist in the project")
            elif isinstance(node, ast.ImportFrom):
                names = [a.name for a in node.names]
                if node.level:                                   # relative import
                    base = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                    module = ".".join(base + ([node.module] if node.module else []))
                    if module:
                        check_from(path, module, names, node.lineno)
                elif node.module and node.module.split(".")[0] in roots:
                    check_from(path, node.module, names, node.lineno)
    return fail("imports_resolve", "; ".join(sorted(set(errors))[:8])) if errors else ok("imports_resolve", f"{len(mods)} module(s)")


_ALIASES = {"yaml": "pyyaml", "pil": "pillow", "sklearn": "scikit_learn", "cv2": "opencv_python", "bs4": "beautifulsoup4",
            "dotenv": "python_dotenv", "jwt": "pyjwt", "jose": "python_jose", "dateutil": "python_dateutil",
            "multipart": "python_multipart", "flask_cors": "flask_cors", "psycopg2": "psycopg2_binary",
            "uvicorn": "uvicorn", "starlette": "starlette"}


def declared_dependencies(files: dict) -> Outcome:
    """Third-party imports should appear in requirements.txt (soft check: import and package
    names differ, so a small alias table is used and unknown cases are not flagged)."""
    req = next((files[p] for p in files if PurePosixPath(p).name == "requirements.txt"), None)
    if req is None:
        return skipped("declared_dependencies", "no requirements.txt")
    declared = set()
    for line in req.splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            declared.add(re.split(r"[<>=!~\[; ]", line)[0].lower().replace("-", "_"))
    mods = _module_index(files)
    roots = {m.split(".")[0] for m in mods}
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    missing = set()
    for path in (p for p in files if p.endswith(".py")):
        try:
            tree = ast.parse(files[path])
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for n in names:
                top = n.split(".")[0]
                if top in stdlib or top in roots:
                    continue
                key = _ALIASES.get(top.lower(), top.lower()).replace("-", "_")
                if key not in declared:
                    missing.add(top)
    return fail("declared_dependencies", f"imported but not in requirements.txt: {sorted(missing)}") if missing \
        else ok("declared_dependencies", f"{len(declared)} declared")


# ----------------------------------------------------------------------- web projects

class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "script" and a.get("src"):
            self.refs.append(a["src"])
        if tag == "link" and a.get("href") and "stylesheet" in (a.get("rel") or ""):
            self.refs.append(a["href"])


def html_refs_resolve(files: dict) -> Outcome:
    """Local <script src> / <link rel=stylesheet href> targets must exist."""
    html = [p for p in files if p.endswith(".html")]
    if not html:
        return skipped("html_refs_resolve", "no .html files")
    missing = []
    for p in html:
        parser = _Refs()
        parser.feed(files[p])
        for ref in parser.refs:
            if _EXTERNAL_REF.match(ref):
                continue
            target = os.path.normpath(os.path.join(os.path.dirname(p), ref.split("?")[0].split("#")[0])).replace("\\", "/")
            if target not in files:
                missing.append(f"{p} -> {ref}")
    return fail("html_refs_resolve", f"missing: {missing}") if missing else ok("html_refs_resolve", f"{len(html)} page(s)")


_ID_REFS = [re.compile(r"""getElementById\(\s*['"]([^'"]+)['"]\s*\)"""),
            re.compile(r"""querySelector(?:All)?\(\s*['"]#([\w-]+)['"]""")]
_ID_DEFS = [re.compile(r"""\bid\s*=\s*\\?["']([\w-]+)"""), re.compile(r"""\.id\s*=\s*['"]([\w-]+)['"]"""),
            re.compile(r"""setAttribute\(\s*['"]id['"]\s*,\s*['"]([\w-]+)['"]""")]


def dom_ids_resolve(files: dict) -> Outcome:
    """Element ids that JS looks up must exist in the HTML (or be created by the JS itself)."""
    html = [p for p in files if p.endswith(".html")]
    js = [p for p in files if p.endswith((".js", ".jsx", ".ts", ".tsx"))]
    if not html or not js:
        return skipped("dom_ids_resolve", "needs both html and js files")
    defined = set()
    for p in html:
        parser = _Refs()
        parser.feed(files[p])
        defined |= parser.ids
    for p in js:
        for rx in _ID_DEFS:
            defined |= set(rx.findall(files[p]))
    missing = sorted({f"{i} (used in {p})" for p in js for rx in _ID_REFS for i in rx.findall(files[p]) if i not in defined})
    return fail("dom_ids_resolve", f"JS looks up ids that no HTML defines: {missing}") if missing else ok("dom_ids_resolve")


# ------------------------------------------------------------------ content heuristics

# A marker is TODO/FIXME/XXX in capitals right after a comment opener, or `todo:`/`fixme:` in any case. Matching them
# case-insensitively after "#" flagged `#todo-list { }` (a CSS id), `href="#todo"` and "/* Todo list styles */" in every
# to-do app. "#" only opens a comment in Python here.
_MARKER = r"(?:(?-i:TODO|FIXME|XXX)\b|(?i:todo|fixme)\s*:)"
_PLACEHOLDER = re.compile(r"(//|/\*|<!--)\s*" + _MARKER + r"|raise\s+NotImplementedError|\b(implement (me|this|here)|your code here)\b", re.I)
_PLACEHOLDER_PY = re.compile(r"#\s*" + _MARKER, re.I)


def no_placeholders(files: dict) -> Outcome:
    """Code must not ship TODO/FIXME comments or NotImplementedError stubs (the coder prompt forbids them)."""
    hits = []
    for p, text in files.items():
        if PurePosixPath(p).suffix not in CODE_EXTS:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _PLACEHOLDER.search(line) or (p.endswith(".py") and _PLACEHOLDER_PY.search(line)):
                hits.append(f"{p}:{i}")
    return fail("no_placeholders", f"placeholders at {hits[:6]}") if hits else ok("no_placeholders")


def _select(files: dict, pattern: Optional[str]) -> dict:
    return files if not pattern else {p: files[p] for p in _match(files, pattern)}


def contains(files: dict, rules: list[dict]) -> Outcome:
    """Each rule: {file?: glob, any?: [...], all?: [...], regex?: str}. Case-insensitive."""
    problems = []
    for r in rules:
        scope = _select(files, r.get("file"))
        blob = "\n".join(scope.values()).lower()
        label = r.get("file") or "<any file>"
        if not scope:
            problems.append(f"{label}: no such file")
            continue
        if r.get("any") and not any(t.lower() in blob for t in r["any"]):
            problems.append(f"{label}: none of {r['any']}")
        if r.get("all") and (m := [t for t in r["all"] if t.lower() not in blob]):
            problems.append(f"{label}: missing {m}")
        if r.get("regex") and not re.search(r["regex"], "\n".join(scope.values()), re.I | re.M):
            problems.append(f"{label}: regex {r['regex']!r} not found")
    return fail("contains", "; ".join(problems)) if problems else ok("contains", f"{len(rules)} rule(s)")


def not_contains(files: dict, rules: list[dict]) -> Outcome:
    """Each rule: {file?: glob, terms: [...]} - none of the terms may appear."""
    problems = []
    for r in rules:
        blob = "\n".join(_select(files, r.get("file")).values()).lower()
        found = [t for t in r["terms"] if t.lower() in blob]
        if found:
            problems.append(f"{r.get('file') or '<any file>'}: {found}")
    return fail("not_contains", "; ".join(problems)) if problems else ok("not_contains")


def _defs(path: str, text: str) -> set:
    if path.endswith(".py"):
        try:
            return {n.name for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        except SyntaxError:
            return set()
    names = set(re.findall(r"\bfunction\s+(\w+)", text)) | set(re.findall(r"\bclass\s+(\w+)", text))
    names |= set(re.findall(r"\b(?:const|let|var)\s+(\w+)\s*=", text))
    return names


def defines(files: dict, rules: list[dict]) -> Outcome:
    """Each rule: {file?|files?: glob(s), names?: [...] (all required), regex?: str (some name matches)}."""
    problems = []
    for r in rules:
        patterns = r.get("files") or [r.get("file")]
        scope = {}
        for pat in patterns:
            scope.update(_select(files, pat))
        have = set().union(*(_defs(p, t) for p, t in scope.items())) if scope else set()
        label = "/".join(str(p) for p in patterns)
        if r.get("names") and (m := [n for n in r["names"] if n not in have]):
            problems.append(f"{label}: missing definitions {m}")
        if r.get("regex") and not any(re.search(r["regex"], n, re.I) for n in have):
            problems.append(f"{label}: no definition matches {r['regex']!r} (have {sorted(have)[:12]})")
    return fail("defines", "; ".join(problems)) if problems else ok("defines", f"{len(rules)} rule(s)")


# ---------------------------------------------------------------- editing: before vs after

def modified(before: dict, after: dict, patterns: list[str]) -> Outcome:
    untouched = [p for p in patterns if not any(_norm(after.get(f, "")) != _norm(before.get(f, ""))
                                                for f in set(_match(after, p)) | set(_match(before, p)))]
    return fail("modified", f"expected changes but unchanged: {untouched}") if untouched else ok("modified")


def unmodified(before: dict, after: dict, patterns: list[str]) -> Outcome:
    touched = sorted(f for p in patterns for f in _match(before, p) if _norm(after.get(f, "")) != _norm(before[f]))
    return fail("unmodified", f"files that should be left alone were changed: {touched}") if touched else ok("unmodified")


def no_files_deleted(before: dict, after: dict, allow: list[str] = ()) -> Outcome:
    gone = sorted(f for f in before if f not in after and not any(fnmatch.fnmatch(f, a) for a in allow))
    return fail("no_files_deleted", f"deleted: {gone}") if gone else ok("no_files_deleted")


def preserved_symbols(before: dict, after: dict, rules: list[dict]) -> Outcome:
    lost = []
    for r in rules:
        f = r["file"]
        had = _defs(f, before.get(f, ""))
        now = _defs(f, after.get(f, ""))
        lost += [f"{f}:{n}" for n in r["names"] if n in had and n not in now]
    return fail("preserved_symbols", f"existing definitions were lost: {lost}") if lost else ok("preserved_symbols")


# --------------------------------------------------------------------------- Q&A answers

def answer_contains(answer: str, groups: list[list[str]]) -> Outcome:
    """Every group must be satisfied by at least one of its alternatives (case-insensitive)."""
    low = answer.lower()
    missing = [g for g in groups if not any(t.lower() in low for t in g)]
    return fail("answer_contains", f"answer lacks any of {missing}") if missing else ok("answer_contains")


def answer_not_contains(answer: str, terms: list[str]) -> Outcome:
    low = answer.lower()
    found = [t for t in terms if t.lower() in low]
    return fail("answer_not_contains", f"answer asserts things that are not in the code: {found}") if found else ok("answer_not_contains")


def answer_max_words(answer: str, limit: int) -> Outcome:
    """For prompts that ask for a short answer ("answer in short")."""
    n = len(answer.split())
    return fail("answer_max_words", f"{n} words, limit {limit}") if n > limit else ok("answer_max_words", f"{n} words")


_ADMITS = re.compile(
    r"(^\W*(no|nope)\b|"                                              # a direct "No." / "No, ..."
    r"\b(nothing|none)\b|"
    r"not (shown|found|present|included|provided|visible|mentioned|implemented|defined|specified|available|contain|"
    r"supported|handled|performed|exposed)|"
    r"\bno (authentication|auth|information|mention|evidence|indication|sign|code|support|such|built-in)|"
    r"(does not|doesn't|do not|don't|did not|didn't|is not|isn't|are not|aren't|cannot|can't) "
    r"(have|include|implement|contain|use|support|appear|show|mention|handle|provide|perform|do|exist|any)|"
    r"there (is|are|'s) no|(couldn't|unable to|cannot|can't) (find|determine|tell|see)|"
    r"\blacks?\b|unclear|not enough)", re.I | re.M)


def admits_unknown(answer: str) -> Outcome:
    """For questions the code cannot answer, the reply must say so rather than invent something."""
    return ok("admits_unknown") if _ADMITS.search(answer) else fail("admits_unknown", "answer does not acknowledge the information is absent")


# ------------------------------------------------------------------------ executable checks

def run_exec_checks(files: dict, checks: list[dict], default_timeout: int = 20) -> list[Outcome]:
    """Run the case's own assertions against the output in a throwaway directory.

    NOT a sandbox: the code under test is LLM output and is executed on this machine.
    It runs with a stripped environment (no API keys), a temp cwd, and a timeout, and
    the harness only does this when asked (`--exec`).
    """
    outcomes = []
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "SystemRoot", "COMSPEC", "PATHEXT")}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    for i, chk in enumerate(checks):
        name = chk.get("name", f"exec_{i + 1}")
        with tempfile.TemporaryDirectory() as td:
            for p, text in files.items():
                dest = Path(td) / p
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
            for p, text in (chk.get("setup_files") or {}).items():
                (Path(td) / p).parent.mkdir(parents=True, exist_ok=True)
                (Path(td) / p).write_text(text, encoding="utf-8")
            cmd = [sys.executable, "-c", chk["snippet"]] if "snippet" in chk else \
                [sys.executable if c == "python" else c for c in chk["cmd"]]
            env_run = {**env, "TEMP": td, "TMP": td}
            try:
                r = subprocess.run(cmd, cwd=td, env=env_run, capture_output=True, text=True,
                                   timeout=chk.get("timeout", default_timeout))
            except subprocess.TimeoutExpired:
                outcomes.append(Outcome(name, "exec", False, "timed out"))
                continue
            missing = [s for s in chk.get("stdout_contains", []) if s.lower() not in r.stdout.lower()]
            if r.returncode != 0:
                tail = (r.stderr.strip().splitlines() or ["(no stderr)"])[-1][:200]
                outcomes.append(Outcome(name, "exec", False, f"exit {r.returncode}: {tail}"))
            elif missing:
                outcomes.append(Outcome(name, "exec", False, f"stdout lacks {missing}; got {r.stdout.strip()[:150]!r}"))
            else:
                outcomes.append(Outcome(name, "exec", True, "ok"))
    return outcomes
