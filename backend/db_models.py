from sqlalchemy import Column, String, DateTime, Text, Integer, Float, ForeignKey, JSON, Enum, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum


Base = declarative_base()


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class ProjectStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionMode(str, enum.Enum):
    GENERATION = "generation"
    EDITING = "editing"
    QUESTION_ANSWERING = "question_answering"


class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)  # OAuth ID
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    avatar_url = Column(String)
    provider = Column(String, nullable=False)  # "google" or "github"
    role = Column(Enum(UserRole), default=UserRole.USER)
    projects_created_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    repositories = relationship("Repository", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    prompt = Column(Text, nullable=False)  # Original user prompt
    
    # Project files stored as JSON: {file_path: content}
    files = Column(JSON, nullable=False, default=dict)
    
    # Metadata
    status = Column(Enum(ProjectStatus), default=ProjectStatus.PENDING)
    error_message = Column(Text)
    integration_fixes = Column(Integer, default=0)  # Number of fixes applied
    repository_id = Column(String, nullable=True)  # repo made from this project ("Open as Repository"), if any
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))  # when the latest generation run began
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="projects")


class Repository(Base):
    __tablename__ = "repositories"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Repository info
    name = Column(String, nullable=False)
    url = Column(String)  # GitHub URL if cloned
    local_path = Column(String)  # Path if uploaded locally
    provider = Column(String)  # "github" or "local"
    
    # Qdrant collection name for this repository
    collection_name = Column(String, unique=True, nullable=False, index=True)

    # Persisted snapshot of indexed file contents, stored as JSON: {file_path: content}.
    # Source of truth for rehydrating local_path after it's wiped (e.g. ephemeral dyno storage).
    files = Column(JSON, nullable=True, default=dict)

    # Indexing status
    is_indexed = Column(Boolean, default=False)
    files_count = Column(Integer, default=0)
    chunks_count = Column(Integer, default=0)
    last_indexed_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="repositories")


class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Session mode and target
    mode = Column(Enum(SessionMode), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=True)
    
    # Conversation history stored as JSON
    messages = Column(JSON, nullable=False, default=list)
    
    # Final result
    result = Column(JSON)  # Agent result
    
    # Status
    is_active = Column(Boolean, default=True)
    completed_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="sessions")


class AgentRun(Base):
    """One execution of an agent graph (generation / editing / Q&A), with what it cost.

    Populated from the in-process `RunMetrics` once a run finishes, so production
    traffic accumulates into a dataset that can be evaluated. Deleting the session
    deletes its runs (the prompt is user content; it must go when the chat does).
    """
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    mode = Column(String, nullable=False, index=True)  # SessionMode value
    user_prompt = Column(Text, nullable=False)
    provider = Column(String)
    model = Column(String)

    status = Column(String, nullable=False, index=True)  # "success" | "failure"
    error_message = Column(Text)

    llm_calls = Column(Integer, default=0, nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False)
    # Sum of the individual LLM calls' latencies, not wall-clock time for the run.
    latency_ms = Column(Float, default=0.0, nullable=False)
    retries = Column(Integer, default=0, nullable=False)
    integration_fixes = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    steps = relationship("RunStep", back_populates="run", cascade="all, delete-orphan", passive_deletes=True)


class RunStep(Base):
    """Per-agent breakdown of an AgentRun (planner, coder, ... each with its own totals)."""
    __tablename__ = "run_steps"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    agent = Column(String, nullable=False)
    calls = Column(Integer, default=0, nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    latency_ms = Column(Float, default=0.0, nullable=False)

    run = relationship("AgentRun", back_populates="steps")


class Feedback(Base):
    """A user's thumbs up/down on one AgentRun (the signal behind the feedback flywheel).

    One rating per (run, user); rating again replaces it. Deleting the run (which happens when its
    session is deleted) or the user deletes the rating, so a comment never outlives the chat it is about.
    """
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("run_id", "user_id", name="uq_feedback_run_user"),)

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    rating = Column(String, nullable=False, index=True)  # "up" | "down"
    comment = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
