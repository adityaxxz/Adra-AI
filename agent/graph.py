import re
from agent.prompts import planner_prompt, architect_prompt, coder_prompt, integrator_prompt, explainer_prompt
from agent.repository.service import search_repository
from agent.state import Plan, TaskPlan, CoderState, CoderOutput, IntegrationResult
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from agent.tools import read_file, write_file, init_project_root, read_sibling_files_context, read_all_project_files
from agent.llm_client import structured_invoke, simple_invoke, truncate_for_context, get_stats


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

    retrieved_context = state.get("retrieved_context", "")
    collection_name = state.get("collection_name", None)

    res = structured_invoke(
        Plan,
        planner_prompt(
            user_prompt=user_prompt,
            retrieved_context=retrieved_context,
        )
    )

    # If repository context exists, search for relevant snippets for each file
    relevant_snippets = {}
    if retrieved_context and hasattr(res, 'files'):
        from agent.repository.service import search_repository
        for file in res.files:
            # Search for code relevant to this file's purpose
            query = f"{file.purpose} {file.path}"
            try:
                results = search_repository(query, k=3, collection_name=collection_name)
                if results:
                    snippets = "\n\n".join(
                        f"FILE: {r.file_path}\n{r.content}"
                        for r in results
                    )
                    relevant_snippets[file.path] = snippets
            except Exception:
                pass

    return {"plan": res, "relevant_code_snippets": relevant_snippets}


def architect_agent(state: dict) -> dict:
    plan: Plan = state["plan"]
    res = structured_invoke(TaskPlan, architect_prompt(plan))
    res.plan = plan
    relevant_snippets = state.get("relevant_code_snippets", {})
    return {"task_plan": res, "relevant_code_snippets": relevant_snippets}


def coder_agent(state: dict) -> dict:
    coder_state = state.get("coder_state")

    if coder_state is None:
        coder_state = CoderState(task_plan=state["task_plan"], current_step_idx=0)
        relevant_snippets = state.get("relevant_code_snippets", {})
        coder_state.relevant_code_snippets = relevant_snippets

    steps = coder_state.task_plan.steps

    if coder_state.current_step_idx >= len(steps):
        return {"coder_state": coder_state, "status": "DONE"}

    curr_task = steps[coder_state.current_step_idx]
    existing_content = read_file.invoke({"path": curr_task.filepath})
    existing_content = truncate_for_context(existing_content)

    project_context = read_sibling_files_context(curr_task.filepath)
    project_context = truncate_for_context(project_context, max_chars=8000)

    # Use file-specific relevant snippets if available, otherwise use general repository context
    repository_context = ""
    if coder_state.relevant_code_snippets and curr_task.filepath in coder_state.relevant_code_snippets:
        repository_context = coder_state.relevant_code_snippets[curr_task.filepath]
    else:
        repository_context = state.get("retrieved_context", "")
    
    repository_context = truncate_for_context(repository_context, max_chars=4000)

    prompt = coder_prompt(
        filepath=curr_task.filepath,
        task_description=curr_task.task_description,
        existing_content=existing_content,
        project_context=project_context,
        plan_summary=_plan_summary(coder_state.task_plan),
        repository_context=repository_context,
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


def repository_agent(state: dict):
    try:
        collection_name = state.get("collection_name", None)
        results = search_repository(state["user_prompt"], collection_name=collection_name)

        context = "\n\n".join(
            f"""
                FILE: {r.file_path}

                {r.content}
            """ for r in results)

    except Exception:
        context = ""

    # Preserve existing state keys
    result = {"retrieved_context": context}
    for key in ["user_prompt", "repo_path", "collection_name"]:
        if key in state:
            result[key] = state[key]
    return result


def explainer_agent(state: dict) -> dict:
    """Answer user's question about the codebase using retrieved context."""
    user_question = state["user_prompt"]
    retrieved_context = state.get("retrieved_context", "")
    
    prompt = explainer_prompt(user_question, retrieved_context)
    answer = simple_invoke(prompt)
    
    return {"answer": answer}


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
repository_editing_graph = StateGraph(dict)
repository_editing_graph.add_node("repository", repository_agent)
repository_editing_graph.add_node("planner", planner_agent)
repository_editing_graph.add_node("architect", architect_agent)
repository_editing_graph.add_node("coder", coder_agent)
repository_editing_graph.add_node("integrator", integrator_agent)

repository_editing_graph.add_edge(START, "repository")
repository_editing_graph.add_edge("repository", "planner")
repository_editing_graph.add_edge("planner", "architect")
repository_editing_graph.add_edge("architect", "coder")

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
