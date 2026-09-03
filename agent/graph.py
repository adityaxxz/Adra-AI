import re
import logging
from langsmith import traceable
from agent.prompts import planner_prompt, edit_planner_prompt, architect_prompt, coder_prompt, integrator_prompt, explainer_prompt
from agent.repository.service import search_repository
from agent.state import Plan, TaskPlan, Architect, EditPlan, CoderState, CoderOutput, IntegrationResult
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from agent.tools import read_file, write_file, init_project_root, read_sibling_files_context, read_selected_project_files, list_project_paths
from agent.llm_client import structured_invoke, simple_invoke, truncate_for_context, get_stats
from agent.observability import langfuse_observe

logger = logging.getLogger(__name__)


def _strip_markdown_fences(content: str) -> str:
    content = content.strip()
    match = re.match(r"^```[\w]*\n(.*)\n```$", content, re.DOTALL)
    if match:
        return match.group(1)
    return content


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
    repo_files = "\n".join(list_project_paths()) or "(no files found)"

    res = structured_invoke(
        EditPlan,
        edit_planner_prompt(
            user_prompt=state["user_prompt"],
            retrieved_context=truncate_for_context(state.get("retrieved_context", ""), max_chars=6000),
            repo_files=truncate_for_context(repo_files, max_chars=4000),
        ),
        agent="edit_planner",
        session_id=state.get("session_id"),
    )

    # The coder loop consumes a TaskPlan, so adapt rather than teaching it a
    # second shape. `edit_summary` is what `_plan_summary` reports downstream.
    task_plan = TaskPlan(
        steps=[
            Architect(filepath=edit.filepath, task_description=edit.change_description)
            for edit in res.edits
        ]
    )
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
    existing_content = read_file.invoke({"path": curr_task.filepath})
    existing_content = truncate_for_context(existing_content)

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
    content = _strip_markdown_fences(result.content)
    write_file.invoke({"path": curr_task.filepath, "content": content})

    coder_state.current_step_idx += 1
    return _carry(state, coder_state=coder_state)


@traceable(name="integrator_agent", run_type="chain")
@langfuse_observe("integrator_agent", as_type="agent")
def integrator_agent(state: dict) -> dict:
    task_plan: TaskPlan = state["coder_state"].task_plan

    # Review only the files this run actually wrote (one per coder step), not the
    # whole tree. In repository editing mode PROJECT_ROOT is a real checkout, so
    # reading everything meant the integrator saw a truncated slice of an
    # unrelated codebase and could still return full-file rewrites for it.
    changed_paths = [step.filepath for step in task_plan.steps]
    project_files = read_selected_project_files(changed_paths)
    project_files = truncate_for_context(project_files, max_chars=12000)

    # Unchanged repo code the changed files depend on, as read-only reference so
    # the integrator doesn't flag symbols it simply wasn't shown.
    reference_context = truncate_for_context(state.get("retrieved_context", ""), max_chars=4000)

    prompt = integrator_prompt(project_files, _plan_summary(task_plan), reference_context)
    result = structured_invoke(IntegrationResult, prompt, agent="integrator", session_id=state.get("session_id"))

    allowed = {p.replace("\\", "/") for p in changed_paths}
    applied = 0
    for update in result.updates:
        if update.filepath.replace("\\", "/") not in allowed:
            logger.warning(
                f"integrator_agent: discarding out-of-scope update for {update.filepath!r} "
                f"(not written by this run)"
            )
            continue
        content = _strip_markdown_fences(update.content)
        write_file.invoke({"path": update.filepath, "content": content})
        applied += 1

    return _carry(state, integration_fixes=applied)


@traceable(name="repository_agent", run_type="chain")
@langfuse_observe("repository_agent", as_type="retriever")
def repository_agent(state: dict):
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
