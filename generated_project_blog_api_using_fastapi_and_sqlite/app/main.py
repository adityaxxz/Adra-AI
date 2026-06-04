from typing import List
from . import crud, models, schemas, database

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from . import crud, models, schemas, database

app = FastAPI()

@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=database.engine)

@app.post("/blogposts", response_model=schemas.BlogPost, status_code=status.HTTP_201_CREATED)
def create_blog_post(
    post: schemas.BlogPostCreate,
    db: Session = Depends(database.get_db)
):
    return crud.create_blog_post(db=db, post=post)

@app.get("/blogposts", response_model=List[schemas.BlogPost])
def get_blog_posts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    posts = crud.get_blog_posts(db=db, skip=skip, limit=limit)
    return posts

@app.get("/blogposts/{post_id}", response_model=schemas.BlogPost)
def get_blog_post(
    post_id: int,
    db: Session = Depends(database.get_db)
):
    db_post = crud.get_blog_post(db=db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
    return db_post

@app.put("/blogposts/{post_id}", response_model=schemas.BlogPost)
def update_blog_post(
    post_id: int,
    post: schemas.BlogPostCreate,
    db: Session = Depends(database.get_db)
):
    db_post = crud.update_blog_post(db=db, post_id=post_id, post=post)
    if db_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
    return db_post

@app.delete("/blogposts/{post_id}", response_model=schemas.BlogPost)
def delete_blog_post(
    post_id: int,
    db: Session = Depends(database.get_db)
):
    db_post = crud.delete_blog_post(db=db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
    return db_post