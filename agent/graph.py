import ast
import json
import re
import logging
from typing import Optional
from langsmith import traceable
from agent.prompts import planner_prompt, edit_planner_prompt, architect_prompt, coder_prompt, integrator_prompt, explainer_prompt
from agent.repository.service import search_repository
from agent.state import Plan, TaskPlan, Architect, EditPlan, CoderState, CoderOutput, IntegrationResult
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from agent.tools import read_file, write_file, init_project_root, read_sibling_files_context, read_selected_project_files, list_project_paths, closest_existing_path
from agent.llm_client import structured_invoke, simple_invoke, truncate_for_context, get_stats
from agent.observability import langfuse_observe
from agent.progress import report_progress
from agent.guardrails import redact_new_secrets

logger = logging.getLogger(__name__)

# The coder and integrator return COMPLETE files, so they must see the whole file they
# rewrite: a cut-off view comes back as a cut-off file, silently dropping everything
# past the cut. These are far above the 10k-char budget used for read-only context
# (that cap is for reference code, not for a file being rewritten). A file over the
# limit is skipped rather than risk truncating it.
MAX_EDIT_FILE_CHARS = 120_000
MAX_INTEGRATOR_CHARS = 120_000
# Budget for the file listing shown to the edit planner. It is alphabetical, so a tight
# cap hides whole directories (src/, tests/) and the planner then invents paths.
MAX_REPO_LISTING_CHARS = 30_000


def _strip_markdown_fences(content: str) -> str:
    content = content.strip()
    # §3.1: prompts wrap repository text in <repository_content> tags; a model that echoes them must not save them.
    tag = re.match(r"^<repository_content>\n?(.*?)\n?</repository_content>$", content, re.DOTALL)
    if tag:
        content = tag.group(1).strip()
    match = re.match(r"^```[\w]*\n(.*)\n```$", content, re.DOTALL)
    if match:
        return match.group(1)
    return content


def _is_valid(filepath: str, text: str) -> Optional[bool]:
    """Whether `text` is valid for the file type, or None when there is no cheap check for it."""
    checks = {".py": ast.parse, ".json": json.loads}
    for ext, check in checks.items():
        if filepath.endswith(ext):
            try:
                check(text)
                return True
            except (SyntaxError, ValueError):
                return False
    return None


_JSON_ESCAPE = re.compile(r'\\(u[0-9a-fA-F]{4}|["\\/bfnrt])')
_SIMPLE_ESCAPES = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}


def _unescape_one(m: re.Match) -> str:
    code = m.group(1)
    return chr(int(code[1:], 16)) if code[0] == 'u' else _SIMPLE_ESCAPES[code]


def _fix_double_escaping(content: str, filepath: str) -> str:
    r"""Undo a file the model returned JSON-escaped twice.

    Sometimes the whole `content` field arrives as one line of literal backslash-n and backslash-quote text
    (seen live on `gen-03-blog-api`, where it left an unparseable app/schemas.py that the integrator did not
    repair). Decode it, but only when that is safe: the text has no real newlines and several literal `\n`
    sequences, and for .py/.json the original is invalid while the decoded text is valid, so a legitimate
    one-line file such as `print("a\nb\nc")` is never touched."""
    body = content.strip()
    if "\n" in body or body.count("\\n") < 3:
        return content
    # Decode the escape sequences themselves rather than parsing the text as one JSON string: the model sometimes
    # leaves a quote unescaped (seen in CI: every quote escaped except the file's opening """), and a JSON parse
    # then rejects the whole file although it is plainly double-escaped.
    fixed = _JSON_ESCAPE.sub(_unescape_one, body)
    if fixed == body:
        return content
    if _is_valid(filepath, content) or _is_valid(filepath, fixed) is False:
        return content
    logger.warning(f"{filepath}: model returned double-escaped content; decoded it ({len(content)} -> {len(fixed)} chars)")
    return fixed


def _fix_escaped_quotes(content: str, filepath: str, existing: str = "") -> str:
    r"""Undo quotes the model backslash-escaped in an otherwise normal file.

    The sibling failure to `_fix_double_escaping`: the newlines are real but every `"` arrives as `\"`
    (seen live: a one-line edit to index.html came back with `lang=\"en\"` on 17 lines, so the page was
    silently corrupted). It is only undone when no plain `"` is left in the file at all, the original used
    plain quotes, and the file is not valid JSON/Python as written, so code that really contains
    escaped quotes is never touched. A new file has no original to compare with, so it needs more evidence."""
    escaped = content.count('\\"')
    if not escaped or content.count('"') != escaped or '\\"' in existing:
        return content
    if existing.count('"') == 0 and escaped < 4:
        return content
    fixed = content.replace('\\"', '"')
    if _is_valid(filepath, content) or _is_valid(filepath, fixed) is False:
        return content
    logger.warning(f"{filepath}: model backslash-escaped every quote; unescaped {escaped} of them")
    return fixed


def _keep_trailing_newline(content: str, existing: str) -> str:
    """Fences are stripped with `.strip()`, which also drops the file's final newline; put it back when
    the file had one, or every edit shows a spurious "no newline at end of file" change on its last line."""
    return content + "\n" if existing.endswith("\n") and not content.endswith("\n") else content


def _carry(state: dict, **updates) -> dict:
    """Forward the incoming state, overlaid with this node's updates.

    `StateGraph(dict)` REPLACES the state with whatever a node returns instead
    of merging into it, so a node returning only its own keys silently drops
    everything upstream set (session_id, retrieved_context, coder_state, ...).
    Every node must route its return through here.
    """
    return {**state, **updates}


def _plan_summary(task_plan: TaskPlan) -> str:
    # Editing plans carry a plain summary; generation plans carry a full Plan.
    edit_summary = getattr(task_plan, "edit_summary", None)
    if edit_summary:
        return edit_summary
    plan = getattr(task_plan, "plan", None)
    if plan is None:
        return "Unknown project"
    return f"{plan.name} — {plan.description} ({plan.techstack})"


@traceable(name="planner_agent", run_type="chain")
@langfuse_observe("planner_agent", as_type="agent")
def planner_agent(state: dict) -> dict:
    """Plan a project generated from scratch. Repository editing uses
    `edit_planner_agent` instead."""
    user_prompt = state["user_prompt"]
    session_id = state.get("session_id")

    res = structured_invoke(
        Plan,
        planner_prompt(user_prompt=user_prompt),
        agent="planner",
        session_id=session_id,
    )

    return _carry(state, plan=res)


@traceable(name="architect_agent", run_type="chain")
@langfuse_observe("architect_agent", as_type="agent")
def architect_agent(state: dict) -> dict:
    plan: Plan = state["plan"]
    res = structured_invoke(TaskPlan, architect_prompt(plan), agent="architect", session_id=state.get("session_id"))
    res.plan = plan
    return _carry(state, task_plan=res)


@traceable(name="edit_planner_agent", run_type="chain")
@langfuse_observe("edit_planner_agent", as_type="agent")
def edit_planner_agent(state: dict) -> dict:
    """Plan file-level edits to an existing repository in one call.

    Replaces planner+architect for editing. Those two were built for greenfield
    generation: the Plan schema's name/description/techstack/features fields are
    meaningful when creating a project but are pure invention for "add a dark
    mode toggle", and the architect pass largely restated the planner's file
    list. Grounding the model in the real file listing is what keeps it from
    planning edits to paths that don't exist.
    """
    report_progress("Planning the changes")
    existing = list_project_paths()
    repo_files = "\n".join(existing) or "(no files found)"

    res = structured_invoke(
        EditPlan,
        edit_planner_prompt(
            user_prompt=state["user_prompt"],
            retrieved_context=truncate_for_context(state.get("retrieved_context", ""), max_chars=6000),
            repo_files=truncate_for_context(repo_files, max_chars=MAX_REPO_LISTING_CHARS),
        ),
        agent="edit_planner",
        session_id=state.get("session_id"),
    )

    # The coder loop consumes a TaskPlan, so adapt rather than teaching it a
    # second shape. `edit_summary` is what `_plan_summary` reports downstream.
    # A misspelt filename in the request ("style.cc") otherwise gets "deliberately
    # created" as a new file. Snap it onto the one real file it's a typo of, unless
    # the user asked for something new.
    wants_new_file = bool(re.search(r"\b(create|new)\b", state["user_prompt"], re.IGNORECASE))
    steps = []
    for edit in res.edits:
        filepath = edit.filepath
        fixed = None if wants_new_file else closest_existing_path(filepath, existing)
        if fixed:
            logger.info(f"edit_planner_agent: {filepath!r} is not in the repo; editing {fixed!r} instead")
            filepath = fixed
        # One step per file: a second entry (or a typo that snapped onto a file already
        # planned) would make the coder rewrite the same file twice, the 2nd time over the 1st.
        duplicate = next((s for s in steps if s.filepath == filepath), None)
        if duplicate:
            logger.info(f"edit_planner_agent: merging a duplicate plan entry for {filepath!r}")
            duplicate.task_description += f"\n{edit.change_description}"
            continue
        steps.append(Architect(filepath=filepath, task_description=edit.change_description))
    task_plan = TaskPlan(steps=steps)
    task_plan.edit_summary = res.summary

    logger.info(
        f"edit_planner_agent: planned {len(res.edits)} file edit(s): "
        f"{[e.filepath for e in res.edits]}"
    )

    return _carry(state, task_plan=task_plan)


@traceable(name="coder_agent", run_type="chain")
@langfuse_observe("coder_agent", as_type="agent")
def coder_agent(state: dict) -> dict:
    coder_state = state.get("coder_state")
    session_id = state.get("session_id")

    if coder_state is None:
        coder_state = CoderState(task_plan=state["task_plan"], current_step_idx=0)

    steps = coder_state.task_plan.steps

    if coder_state.current_step_idx >= len(steps):
        return _carry(state, coder_state=coder_state, status="DONE")

    curr_task = steps[coder_state.current_step_idx]
    report_progress(f"Writing {curr_task.filepath} ({coder_state.current_step_idx + 1} of {len(steps)})")
    existing_content = read_file.invoke({"path": curr_task.filepath})
    if len(existing_content) > MAX_EDIT_FILE_CHARS or existing_content.startswith("[Binary file skipped") or "\x00" in existing_content:
        logger.warning(f"coder_agent: not editing {curr_task.filepath!r} (binary or over {MAX_EDIT_FILE_CHARS} chars)")
        coder_state.current_step_idx += 1
        return _carry(
            state, coder_state=coder_state,
            skipped_files=[*state.get("skipped_files", []), curr_task.filepath],
        )

    project_context = read_sibling_files_context(curr_task.filepath)
    project_context = truncate_for_context(project_context, max_chars=8000)

    # Repo-wide related code from retrieval (empty in generation mode). The
    # file being edited is read from disk above, so it needs no RAG excerpt.
    repository_context = truncate_for_context(state.get("retrieved_context", ""), max_chars=4000)

    prompt = coder_prompt(
        filepath=curr_task.filepath,
        task_description=curr_task.task_description,
        existing_content=existing_content,
        project_context=project_context,
        plan_summary=_plan_summary(coder_state.task_plan),
        repository_context=repository_context,
    )

    result = structured_invoke(CoderOutput, prompt, agent="coder", session_id=session_id)
    content = _fix_double_escaping(_strip_markdown_fences(result.content), curr_task.filepath)
    content = _fix_escaped_quotes(content, curr_task.filepath, existing_content)
    content = _keep_trailing_newline(content, existing_content)
    content, secrets = redact_new_secrets(content, existing_content)       # §3.1: no new credentials in written files
    write_file.invoke({"path": curr_task.filepath, "content": content})

    coder_state.current_step_idx += 1
    if secrets:
        return _carry(state, coder_state=coder_state,
                      redacted_secrets=[*state.get("redacted_secrets", []), {"file": curr_task.filepath, "kinds": secrets}])
    return _carry(state, coder_state=coder_state)


@traceable(name="integrator_agent", run_type="chain")
@langfuse_observe("integrator_agent", as_type="agent")
def integrator_agent(state: dict) -> dict:
    report_progress("Checking everything fits together")
    task_plan: TaskPlan = state["coder_state"].task_plan

    # Review only the files this run actually wrote (one per coder step), not the
    # whole tree. In repository editing mode PROJECT_ROOT is a real checkout, so
    # reading everything meant the integrator saw a truncated slice of an
    # unrelated codebase and could still return full-file rewrites for it.
    skipped = set(state.get("skipped_files", []))
    changed_paths = [step.filepath for step in task_plan.steps if step.filepath not in skipped]
    # Show each file whole or not at all (see MAX_INTEGRATOR_CHARS): it may only update
    # files it was shown in full, since an update replaces the entire file.
    shown, used = [], 0
    for path in changed_paths:
        size = len(read_file.invoke({"path": path}))
        if used + size <= MAX_INTEGRATOR_CHARS:
            shown.append(path)
            used += size
    if not shown:
        return _carry(state, integration_fixes=0)
    project_files = read_selected_project_files(shown)

    # Unchanged repo code the changed files depend on, as read-only reference so
    # the integrator doesn't flag symbols it simply wasn't shown.
    reference_context = truncate_for_context(state.get("retrieved_context", ""), max_chars=4000)

    # Editing runs always carry the repository they edit; a run without one generates a new project.
    prompt = integrator_prompt(project_files, _plan_summary(task_plan), reference_context, new_project=not state.get("repo_path"))
    result = structured_invoke(IntegrationResult, prompt, agent="integrator", session_id=state.get("session_id"))

    allowed = {p.replace("\\", "/") for p in shown}
    applied = 0
    redacted = []
    for update in result.updates:
        if update.filepath.replace("\\", "/") not in allowed:
            logger.warning(
                f"integrator_agent: discarding out-of-scope update for {update.filepath!r} "
                f"(not written by this run)"
            )
            continue
        content = _fix_double_escaping(_strip_markdown_fences(update.content), update.filepath)
        current = read_file.invoke({"path": update.filepath})
        content = _keep_trailing_newline(_fix_escaped_quotes(content, update.filepath, current), current)
        content, secrets = redact_new_secrets(content, current)
        if secrets:
            redacted.append({"file": update.filepath, "kinds": secrets})
        write_file.invoke({"path": update.filepath, "content": content})
        applied += 1

    if redacted:
        return _carry(state, integration_fixes=applied, redacted_secrets=[*state.get("redacted_secrets", []), *redacted])
    return _carry(state, integration_fixes=applied)


@traceable(name="repository_agent", run_type="chain")
@langfuse_observe("repository_agent", as_type="retriever")
def repository_agent(state: dict):
    report_progress("Searching your codebase")
    try:
        collection_name = state.get("collection_name", None)
        results = search_repository(state["user_prompt"], collection_name=collection_name)

        context = "\n\n".join(
            f"""
                FILE: {r.file_path}

                {r.content}
            """ for r in results)

    except Exception as e:
        logger.warning(f"repository_agent: context retrieval failed, proceeding without repo context: {e}")
        context = ""

    return _carry(state, retrieved_context=context)


@traceable(name="explainer_agent", run_type="chain")
@langfuse_observe("explainer_agent", as_type="agent")
def explainer_agent(state: dict) -> dict:
    """Answer user's question about the codebase using retrieved context."""
    user_question = state["user_prompt"]
    retrieved_context = state.get("retrieved_context", "")

    report_progress("Writing an answer")
    prompt = explainer_prompt(user_question, retrieved_context)
    answer = simple_invoke(prompt, agent="explainer", session_id=state.get("session_id"))

    return _carry(state, answer=answer)


# Project Generation Graph (no repository context)
project_generation_graph = StateGraph(dict)
project_generation_graph.add_node("planner", planner_agent)
project_generation_graph.add_node("architect", architect_agent)
project_generation_graph.add_node("coder", coder_agent)
project_generation_graph.add_node("integrator", integrator_agent)

project_generation_graph.add_edge(START, "planner")
project_generation_graph.add_edge("planner", "architect")
project_generation_graph.add_edge("architect", "coder")

project_generation_graph.add_conditional_edges(
    "coder",
    lambda s: "integrator" if s.get("status") == "DONE" else "coder",
    {"integrator": "integrator", "coder": "coder"},
)
project_generation_graph.add_edge("integrator", END)

project_generation_agent = project_generation_graph.compile()

# Repository Editing Graph (with repository context)
# Uses edit_planner instead of planner+architect: one grounded planning call
# scoped to changing files that already exist. See `edit_planner_agent`.
repository_editing_graph = StateGraph(dict)
repository_editing_graph.add_node("repository", repository_agent)
repository_editing_graph.add_node("edit_planner", edit_planner_agent)
repository_editing_graph.add_node("coder", coder_agent)
repository_editing_graph.add_node("integrator", integrator_agent)

repository_editing_graph.add_edge(START, "repository")
repository_editing_graph.add_edge("repository", "edit_planner")
repository_editing_graph.add_edge("edit_planner", "coder")

repository_editing_graph.add_conditional_edges(
    "coder",
    lambda s: "integrator" if s.get("status") == "DONE" else "coder",
    {"integrator": "integrator", "coder": "coder"},
)
repository_editing_graph.add_edge("integrator", END)

repository_editing_agent = repository_editing_graph.compile()

# Question Answering Graph (ask about project without editing)
question_answering_graph = StateGraph(dict)
question_answering_graph.add_node("repository", repository_agent)
question_answering_graph.add_node("explainer", explainer_agent)

question_answering_graph.add_edge(START, "repository")
question_answering_graph.add_edge("repository", "explainer")
question_answering_graph.add_edge("explainer", END)

question_answering_agent = question_answering_graph.compile()

# Legacy: keep original agent for backward compatibility
agent = project_generation_agent
