from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class File(BaseModel):
    path: str = Field(description="The path to the file to be created or modified")
    purpose: str = Field(description="The purpose of the file, e.g. 'main application logic', 'data processing module', etc.")


class Plan(BaseModel):
    name: str = Field(description="The name of app to be built")
    description: str = Field(description="A oneline description of the app to be built, e.g. 'A web application for managing personal finances'")
    techstack: str = Field(description="The tech stack to be used for the app, e.g. 'python', 'javascript', 'react', 'flask', etc.")
    features: list[str] = Field(description="A list of features that the app should have, e.g. 'user authentication', 'data visualization', etc.")
    files: list[File] = Field(description="A list of files to be created, each with a 'path' and 'purpose'")

class Architect(BaseModel):
    filepath: str=Field(description="The path to the file to be modified")
    task_description: str = Field(description="A detailed description of the task to be performed on the file, e.g. 'add user authentication', 'implement data processing logic', etc.")


class TaskPlan(BaseModel):
    steps: list[Architect] = Field(description="A list of steps to be taken to implement the task")
    model_config = ConfigDict(extra="allow")   #allows extra additional fields passed during model instantiation, store within the model instance 


class CoderOutput(BaseModel):
    content: str = Field(description="The complete file content to write (full file, not a diff or snippet)")


class FileUpdate(BaseModel):
    filepath: str = Field(description="Path of the file to update")
    content: str = Field(description="Corrected full file content")


class IntegrationResult(BaseModel):
    updates: list[FileUpdate] = Field(
        description="Files that need correction for cross-file integration. Empty list if everything works."
    )


class CoderState(BaseModel):
    task_plan: TaskPlan = Field(description="The plan for the task to be implemented")
    current_step_idx: int = Field(0, description="The index of the current step in the implementation steps")
    current_file_content: Optional[str] = Field(None, description="The content of the file currently being edited or created")


class RetrievedContext(BaseModel):
    file_path: str
    content: str
    score: float

class RepositoryContext(BaseModel):
    chunks: list[RetrievedContext]