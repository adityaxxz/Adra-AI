from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, JSON, Enum, Boolean
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
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
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
