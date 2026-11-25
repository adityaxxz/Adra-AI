from agent.prompts import architect_prompt, coder_prompt, explainer_prompt, planner_prompt


def test_explainer_is_told_to_honour_a_requested_length_over_thoroughness():
    """The eval case 'what is this project about answer in short' (a real prompt) got a 141-word reply
    with a table, because the only length instruction was 'concise but thorough'."""
    p = explainer_prompt("what is this project about answer in short", "ctx")
    assert '"in short"' in p and "two or three sentences" in p
    assert "no headings, tables or bullet lists" in p
    assert "what is this project about answer in short" in p and "ctx" in p


def test_the_planner_is_told_to_plan_a_dependency_manifest():
    """Eval gen-03 (a FastAPI + SQLite blog) shipped no requirements.txt in one attempt and one without SQLAlchemy in another."""
    p = planner_prompt("a blog api")
    assert "requirements.txt" in p and "package.json" in p and "MUST include" in p


def test_the_architect_orders_the_manifest_last_and_says_what_it_must_list():
    p = architect_prompt("plan")
    assert "ALWAYS the LAST step" in p and "requirements.txt" in p
    assert "every third-party package" in p


def test_the_coder_derives_a_manifest_from_the_files_it_can_see():
    p = coder_prompt(filepath="requirements.txt", task_description="deps", existing_content="", project_context="# app/db.py", plan_summary="x")
    assert "dependency manifest" in p and "EVERY third-party package" in p and "SQLAlchemy" in p
