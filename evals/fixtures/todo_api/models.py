from pydantic import BaseModel


class TodoCreate(BaseModel):
    title: str


class Todo(BaseModel):
    id: int
    title: str
    done: bool = False
