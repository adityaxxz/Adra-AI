from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from prompts import planner_prompt, architect_prompt, coder_prompt
from state import Plan, Architect, TaskPlan, CoderState
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from tools import *
from langchain.agents import create_agent

from dotenv import load_dotenv
load_dotenv()

# llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# def structured_llm(schema):
#     """Groq gpt-oss models work reliably with json_schema, not function_calling."""
#     return llm.with_structured_output(schema, method="json_schema")


def planner_agent(state: dict) -> dict:
    user_prompt = state["user_prompt"]
    res = llm.with_structured_output(Plan).invoke(planner_prompt(user_prompt)) 

    if res is None:
        raise ValueError("Planner didn't return a valid response")
    return {"plan": res}

def architect_agent(state:dict) -> dict:
    plan: Plan = state["plan"]
    res = llm.with_structured_output(TaskPlan).invoke(architect_prompt(plan))

    if res is None:
        raise ValueError("Architect didn't return a valid response")
    
    res.plan = plan     #adding the previous `plan` context

    return {"task_plan": res}

def coder_agent(state: dict) -> dict:
    coder_state = state.get("coder_state")

    if coder_state is None:
        coder_state = CoderState(task_plan=state["task_plan"], current_step_idx=0)

    steps = coder_state.task_plan.steps

    if coder_state.current_step_idx >= len(steps):  
        return {"coder_state": coder_state, "status": "DONE"}

    curr_task = steps[coder_state.current_step_idx]
    existing_content= read_file.run(curr_task.filepath)  #reads the curr content of the file

    user_prompt = (
        f"Task: {curr_task.task_description}\n"
        f"File: {curr_task.filepath}\n"
        f"Existing content:\n{existing_content}\n"
        "Use write_file(path, content) to save your changes."
    )

    system_prompt = coder_prompt()

    coder_tools = [read_file, write_file, list_files, get_current_directory]

    agent = create_agent(llm , coder_tools)

    agent.invoke({"messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
    })
    
    coder_state.current_step_idx += 1

    return {"coder_state": coder_state}

graph = StateGraph(dict)

graph.add_node("planner", planner_agent)
graph.add_node("architect", architect_agent)
graph.add_node("coder", coder_agent)

# graph.set_entry_point("planner")
graph.add_edge(START, "planner")
graph.add_edge("planner", "architect")
graph.add_edge("architect", "coder")

graph.add_conditional_edges(
    "coder", 
    lambda s: "END" if s.get("status") == "DONE" else "coder",
    {"END": END, "coder": "coder"}
)

agent = graph.compile()


if __name__ == "__main__":

    user_prompt = "create a simple calculator web application."
    result = agent.invoke({"user_prompt": user_prompt},{"recursion_limit": 100})

    print(result)