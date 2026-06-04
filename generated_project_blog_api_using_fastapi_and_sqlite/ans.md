Answer: The project implements all standard CRUD operations for `BlogPost` resources. These operations are exposed via FastAPI endpoints in `app/main.py` and handled by corresponding functions in `app/crud.py` for database interaction.

Here are the implemented CRUD operations with their function names:

### Create (C)

*   **API Endpoint:** `create_blog_post`
    *   **File:** `app/main.py`
    *   **Snippet:**
        ```python
        @app.post("/blogposts", response_model=schemas.BlogPost, status_code=status.HTTP_201_CREATED)
        def create_blog_post(
            post: schemas.BlogPostCreate,
            db: Session = Depends(database.get_db)
        ):
            return crud.create_blog_post(db=db, post=post)
        ```
*   **CRUD Function:** `create_blog_post`
    *   **File:** `app/crud.py`
    *   **Snippet:**
        ```python
        def create_blog_post(db: Session, post: schemas.BlogPostCreate) -> models.BlogPost:    
            db_post = models.BlogPost(title=post.title, content=post.content, published=post.published)
            db.add(db_post)
            db.commit()
            db.refresh(db_post)
            return db_post
        ```
    *   **Explanation:** This function creates a new `BlogPost` entry in the database based on the provided `post` schema.

### Read (R)

*   **API Endpoint (Get all):** `get_blog_posts`
    *   **File:** `app/main.py`
    *   **Snippet:**
        ```python
        @app.get("/blogposts", response_model=List[schemas.BlogPost])
        def get_blog_posts(
            skip: int = 0,
            limit: int = 100,
            db: Session = Depends(database.get_db)
        ):
            posts = crud.get_blog_posts(db=db, skip=skip, limit=limit)
            return posts
        ```
*   **API Endpoint (Get by ID):** `get_blog_post`
    *   **File:** `app/main.py`
    *   **Snippet:**
        ```python
        @app.get("/blogposts/{post_id}", response_model=schemas.BlogPost)
        def get_blog_post(
            post_id: int,
            db: Session = Depends(database.get_db)
        ):
            db_post = crud.get_blog_post(db=db, post_id=post_id)
            # ... error handling ...
            return db_post
        ```
*   **CRUD Function (Get all):** `get_blog_posts`
    *   **File:** `app/crud.py`
    *   **Snippet:**
        ```python
        def get_blog_posts(db: Session, skip: int = 0, limit: int = 100) -> List[models.BlogPost]:
            return db.query(models.BlogPost).offset(skip).limit(limit).all()
        ```
*   **CRUD Function (Get by ID):** `get_blog_post`
    *   **File:** `app/crud.py`
    *   **Snippet:**
        ```python
        def get_blog_post(db: Session, post_id: int) -> models.BlogPost | None:
            return db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()     
        ```
    *   **Explanation:** These functions retrieve either a list of all blog posts (with optional skip and limit for pagination) or a single blog post by its unique `post_id`.

### Update (U)

*   **API Endpoint:** `update_blog_post`
    *   **File:** `app/main.py`
    *   **Snippet:**
        ```python
        @app.put("/blogposts/{post_id}", response_model=schemas.BlogPost)
        def update_blog_post(
            post_id: int,
            post: schemas.BlogPostCreate,
            db: Session = Depends(database.get_db)
        ):
            db_post = crud.update_blog_post(db=db, post_id=post_id, post=post)
            # ... error handling ...
            return db_post
        ```
*   **CRUD Function:** `update_blog_post`
    *   **File:** `app/crud.py`
    *   **Snippet:**
        ```python
        def update_blog_post(db: Session, post_id: int, post: schemas.BlogPostCreate) -> models.BlogPost | None:
            db_post = db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()  
            if db_post:
                db_post.title = post.title
                db_post.content = post.content
                db_post.published = post.published
                db.commit()
                db.refresh(db_post)
            return db_post
        ```
    *   **Explanation:** This function updates an existing `BlogPost` identified by `post_id` with the new data provided in the `post` schema.

### Delete (D)

*   **API Endpoint:** `delete_blog_post`
    *   **File:** `app/main.py`
    *   **Snippet:**
        ```python
        @app.delete("/blogposts/{post_id}", response_model=schemas.BlogPost)
        def delete_blog_post(
            post_id: int,
            db: Session = Depends(database.get_db)
        ):
            db_post = crud.delete_blog_post(db=db, post_id=post_id)
            # ... error handling ...
            return db_post
        ```
*   **CRUD Function:** `delete_blog_post`
    *   **File:** `app/crud.py`
    *   **Snippet:**
        ```python
        def delete_blog_post(db: Session, post_id: int) -> models.BlogPost | None:
            db_post = db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()  
            if db_post:
                db.delete(db_post)
                db.commit()
            return db_post
        ```
    *   **Explanation:** This function deletes a `BlogPost` from the database based on its `post_id`.