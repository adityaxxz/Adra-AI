from sqlalchemy import Column, Integer, String, Boolean

from .database import Base

class BlogPost(Base):
    __tablename__ = "blogposts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(String)
    published = Column(Boolean, default=True)