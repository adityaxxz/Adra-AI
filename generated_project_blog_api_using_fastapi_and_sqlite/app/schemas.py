from pydantic import BaseModel

class BlogPostBase(BaseModel):
    title: str
    content: str
    published: bool = True

class BlogPostCreate(BlogPostBase):
    pass

class BlogPost(BlogPostBase):
    id: int

    class Config:
        orm_mode = True