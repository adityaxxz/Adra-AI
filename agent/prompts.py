
def planner_prompt(user_prompt: str) -> str:
    
    prompt = f""" You are PLANNER agent, convert by USER prompt into a complete engineering project plan 

                user request : {user_prompt}"""
    
    return prompt