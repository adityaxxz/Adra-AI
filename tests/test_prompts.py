from agent.prompts import explainer_prompt


def test_explainer_is_told_to_honour_a_requested_length_over_thoroughness():
    """The eval case 'what is this project about answer in short' (a real prompt) got a 141-word reply
    with a table, because the only length instruction was 'concise but thorough'."""
    p = explainer_prompt("what is this project about answer in short", "ctx")
    assert '"in short"' in p and "two or three sentences" in p
    assert "no headings, tables or bullet lists" in p
    assert "what is this project about answer in short" in p and "ctx" in p
