from langchain_groq import ChatGroq
from prompts import planner_prompt
from state import Plan

from dotenv import load_dotenv
load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b")

user_prompt = "create a simple calculator web application"

prompt = planner_prompt(user_prompt)

structed_llm = llm.with_structured_output(Plan)

chat = structed_llm.invoke(planner_prompt)

print(chat)

