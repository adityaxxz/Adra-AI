from fastapi import FastAPI, HTTPException

import storage
from models import Todo, TodoCreate

app = FastAPI(title="Todo API")


@app.get("/todos", response_model=list[Todo])
def list_todos():
    """Return every todo."""
    return storage.load_todos()


@app.post("/todos", response_model=Todo, status_code=201)
def create_todo(payload: TodoCreate):
    """Create a todo from a title."""
    return storage.add_todo(payload.title)


@app.put("/todos/{todo_id}/done", response_model=Todo)
def complete_todo(todo_id: int):
    """Mark a todo as done. 404 if it does not exist."""
    todo = storage.mark_done(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo
