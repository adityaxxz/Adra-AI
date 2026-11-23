"""Todo persistence: a single JSON file on disk."""
import json
import os

DATA_FILE = "todos.json"


def load_todos() -> list[dict]:
    """Read all todos from DATA_FILE."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_todos(todos: list[dict]) -> None:
    """Write all todos to DATA_FILE."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, indent=2)


def add_todo(title: str) -> dict:
    """Append a new, not-done todo and return it."""
    todos = load_todos() if os.path.exists(DATA_FILE) else []
    todo = {"id": len(todos) + 1, "title": title, "done": False}
    todos.append(todo)
    save_todos(todos)
    return todo


def mark_done(todo_id: int):
    """Mark a todo as done and return it, or None if no todo has that id."""
    todos = load_todos()
    for todo in todos:
        if todo["id"] == todo_id:
            todo["done"] = True
            save_todos(todos)
            return todo
    return None
