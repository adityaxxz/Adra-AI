from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from prompts import planner_prompt, architect_prompt
from state import Plan, Architect, TaskPlan
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from dotenv import load_dotenv
load_dotenv()

# llm = ChatGroq(model="openai/gpt-oss-120b")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

user_prompt = "create a simple calculator web application"

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



graph = StateGraph(dict)

graph.add_node("planner", planner_agent)
graph.add_node("architect", architect_agent)
graph.add_node("coder", coder_agent)

# graph.set_entry_point("planner")
graph.add_edge(START, "planner")
graph.add_edge("planner", "architect")
graph.add_edge("architect", "coder")
graph.add_edge("coder", END)


agent = graph.compile()
result = agent.invoke({"user_prompt": user_prompt})

print(result)