from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from prompts import planner_prompt, architect_prompt, coder_prompt
from state import Plan, Architect, TaskPlan
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from tools import *
from langchain.agents import create_agent

from dotenv import load_dotenv
load_dotenv()

# llm = ChatGroq(model="openai/gpt-oss-120b")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")


def planner_agent(state: dict) -> dict:
    user_prompt = state["user_prompt"]
    structured_llm = llm.with_structured_output(Plan)
    res = structured_llm.invoke(planner_prompt(user_prompt)) 

    if res is None:
        raise ValueError("Planner didn't return a valid response")
    return {"plan": res}

def architect_agent(state:dict) -> dict:
    plan: Plan = state["plan"]
    structured_llm = llm.with_structured_output(TaskPlan)
    res = structured_llm.invoke(architect_prompt(plan))

    if res is None:
        raise ValueError("Architect didn't return a valid response")
    
    res.plan = plan     #adding the previous `plan` context

    return {"task_plan": res}

def coder_agent(state: dict) -> dict:
    steps = state["task_plan"].steps
    curr_step_idx = 0

    curr_task = steps[curr_step_idx]
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
    

    return {}

graph = StateGraph(dict)

graph.add_node("planner", planner_agent)
graph.add_node("architect", architect_agent)
graph.add_node("coder", coder_agent)

# graph.set_entry_point("planner")
graph.add_edge(START, "planner")
graph.add_edge("planner", "architect")
graph.add_edge("architect", "coder")
graph.add_edge("coder", END)



user_prompt = "create a simple calculator web application"

agent = graph.compile()
result = agent.invoke({"user_prompt": user_prompt})

print(result)