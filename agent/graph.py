import re
from agent.prompts import planner_prompt, architect_prompt, coder_prompt, integrator_prompt
from agent.state import Plan, TaskPlan, CoderState, CoderOutput, IntegrationResult
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from agent.tools import read_file, write_file, init_project_root, read_sibling_files_context, read_all_project_files
from agent.llm_client import structured_invoke, truncate_for_context, get_stats

init_project_root()


def _strip_markdown_fences(content: str) -> str:
    content = content.strip()
    match = re.match(r"^```[\w]*\n(.*)\n```$", content, re.DOTALL)
    if match:
        return match.group(1)
    return content


def _plan_summary(task_plan: TaskPlan) -> str:
    plan = getattr(task_plan, "plan", None)
    if plan is None:
        return "Unknown project"
    return f"{plan.name} — {plan.description} ({plan.techstack})"


def planner_agent(state: dict) -> dict:
    user_prompt = state["user_prompt"]
    res = structured_invoke(Plan, planner_prompt(user_prompt))
    return {"plan": res}


def architect_agent(state: dict) -> dict:
    plan: Plan = state["plan"]
    res = structured_invoke(TaskPlan, architect_prompt(plan))
    res.plan = plan
    return {"task_plan": res}


def coder_agent(state: dict) -> dict:
    coder_state = state.get("coder_state")

    if coder_state is None:
        coder_state = CoderState(task_plan=state["task_plan"], current_step_idx=0)

    steps = coder_state.task_plan.steps

    if coder_state.current_step_idx >= len(steps):
        return {"coder_state": coder_state, "status": "DONE"}

    curr_task = steps[coder_state.current_step_idx]
    existing_content = read_file.invoke({"path": curr_task.filepath})
    existing_content = truncate_for_context(existing_content)

    project_context = read_sibling_files_context(curr_task.filepath)
    project_context = truncate_for_context(project_context, max_chars=8000)

    prompt = coder_prompt(
        filepath=curr_task.filepath,
        task_description=curr_task.task_description,
        existing_content=existing_content,
        project_context=project_context,
        plan_summary=_plan_summary(coder_state.task_plan),
    )

    result = structured_invoke(CoderOutput, prompt)
    content = _strip_markdown_fences(result.content)
    write_file.invoke({"path": curr_task.filepath, "content": content})

    coder_state.current_step_idx += 1
    return {"coder_state": coder_state}


def integrator_agent(state: dict) -> dict:
    task_plan: TaskPlan = state["coder_state"].task_plan
    project_files = read_all_project_files()
    project_files = truncate_for_context(project_files, max_chars=12000)

    prompt = integrator_prompt(project_files, _plan_summary(task_plan))
    result = structured_invoke(IntegrationResult, prompt)

    for update in result.updates:
        content = _strip_markdown_fences(update.content)
        write_file.invoke({"path": update.filepath, "content": content})

    return {"integration_fixes": len(result.updates)}


graph = StateGraph(dict)

graph.add_node("planner", planner_agent)
graph.add_node("architect", architect_agent)
graph.add_node("coder", coder_agent)
graph.add_node("integrator", integrator_agent)

graph.add_edge(START, "planner")
graph.add_edge("planner", "architect")
graph.add_edge("architect", "coder")

graph.add_conditional_edges(
    "coder",
    lambda s: "integrator" if s.get("status") == "DONE" else "coder",
    {"integrator": "integrator", "coder": "coder"},
)
graph.add_edge("integrator", END)

agent = graph.compile()
