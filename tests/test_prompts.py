from agent.prompts import architect_prompt, coder_prompt, explainer_prompt, integrator_prompt, planner_prompt


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


def test_the_architect_plans_table_creation_for_orm_projects():
    """Eval gen-03: 2 of 3 generated blog APIs never called create_all, so the first request failed with 'no such table'."""
    p = architect_prompt("plan")
    assert "create_all" in p and "entry point" in p and "no such table" in p


def test_the_integrator_checks_table_creation_only_for_new_projects():
    """An existing repository may create its tables with migrations; telling the integrator to add create_all there
    would be wrong."""
    assert "create_all" in integrator_prompt("files", "plan", new_project=True)
    assert "create_all" not in integrator_prompt("files", "plan", "reference code")
    assert "create_all" not in integrator_prompt("files", "plan")
