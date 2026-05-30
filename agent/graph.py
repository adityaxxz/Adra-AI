from langchain_groq import ChatGroq
from prompts import planner_prompt
from state import Plan
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from dotenv import load_dotenv
load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b")

user_prompt = "create a simple calculator web application"

def planner_agent(state: dict) -> dict:
    user_prompt = state["user_prompt"]
    structed_llm = llm.with_structured_output(Plan)
    res = structed_llm.invoke(planner_prompt(user_prompt)) 
    return {"plan": res}


graph = StateGraph(dict)

graph.add_node("planner", planner_agent)
# graph.set_entry_point("planner")

graph.add_edge(START, "planner")
graph.add_edge("planner", END)


agent = graph.compile()
result = agent.invoke({"user_prompt": user_prompt})

print(result)

