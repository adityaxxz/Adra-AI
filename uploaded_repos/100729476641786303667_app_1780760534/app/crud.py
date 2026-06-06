from sqlalchemy.orm import Session
from typing import List
from . import models, schemas

def create_blog_post(db: Session, post: schemas.BlogPostCreate) -> models.BlogPost:
    db_post = models.BlogPost(title=post.title, content=post.content, published=post.published)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

def get_blog_post(db: Session, post_id: int) -> models.BlogPost | None:
    return db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()

def get_blog_posts(db: Session, skip: int = 0, limit: int = 100) -> List[models.BlogPost]:
    return db.query(models.BlogPost).offset(skip).limit(limit).all()

def update_blog_post(db: Session, post_id: int, post: schemas.BlogPostCreate) -> models.BlogPost | None:
    db_post = db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()
    if db_post:
        db_post.title = post.title
        db_post.content = post.content
        db_post.published = post.published
        db.commit()
        db.refresh(db_post)
    return db_post

def delete_blog_post(db: Session, post_id: int) -> models.BlogPost | None:
    db_post = db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()
    if db_post:
        db.delete(db_post)
        db.commit()
    return db_post