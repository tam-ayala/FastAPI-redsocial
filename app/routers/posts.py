from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import col, select, func, Session

from dependencies import CurrentUser, SessionDep, get_post_or_404, is_admin, require
from models import Post, PostCreate, PostPublic, PostUpdate, PostWithLikes, UserPublic, Like, User

router = APIRouter(prefix="/posts", tags=["posts"])

# ═══════════════ Lectura de posts CON la cuenta de likes ═══════════════
def posts_with_likes():
    """SELECT posts.*, COUNT(likes.user_id)
        FROM posts LEFT JOIN likes ON likes.post_id = posts.id
        GROUP BY posts.id"""
    return (
          select(Post, func.count(col(Like.user_id)))
          .join(Like, col(Like.post_id) == col(Post.id), isouter=True)
          .group_by(col(Post.id))
    )

def to_post_with_likes(row) -> PostWithLikes:
    post, likes_count = row        # cada fila es una tupla (Post, int)
    return PostWithLikes.model_validate(post, update={"likes_count": likes_count})

def get_post_with_likes_or_404(db: Session, post_id: int) -> PostWithLikes:
    row = db.exec(posts_with_likes().where(Post.id == post_id)).first()
    #   → si row es None: 404 "Post no encontrado"; si no: return to_post_with_likes(row)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post no encontrado")
    return to_post_with_likes(row)

#   Pregunta: ¿por qué isouter=True? Prueba quitarlo y mira qué pasa con un post sin likes. - significa que la tabla de likes es opcional, y si no hay likes, igual devuelve el post con 0 likes. Si lo quitas, no devuelve los posts sin likes.
@router.get("", response_model=list[PostWithLikes])
def read_posts(db: SessionDep, offset: int = 0, limit: Annotated[int, Query(le=100)] = 20):
    #stmt = select(Post).order_by(col(Post.created_at).desc()).offset(offset).limit(limit)
    stmt = posts_with_likes().order_by(col(Post.created_at).desc()).offset(offset).limit(limit)
    return [to_post_with_likes(row) for row in db.exec(stmt).all()]


@router.get("/{post_id}", response_model=PostWithLikes)
def read_post(post_id: int, db: SessionDep):
    return get_post_with_likes_or_404(db, post_id)



@router.get("", response_model=list[PostPublic])
def read_posts(db: SessionDep, offset: int = 0, limit: Annotated[int, Query(le=100)] = 20):
    stmt = select(Post).order_by(col(Post.created_at).desc()).offset(offset).limit(limit)
    return db.exec(stmt).all()


@router.get("/{post_id}", response_model=PostPublic)
def read_post(post_id: int, db: SessionDep):
    return get_post_or_404(db, post_id)


@router.post("", response_model=PostPublic, status_code=201)
def create_post(data: PostCreate, db: SessionDep, current_user: CurrentUser):
    post = Post(**data.model_dump(), author_id= current_user.id) #el autor sale del TOKEN, no del cuerpo
    db.add(post)
    db.commit()
    db.refresh(post)
    return post
    

@router.patch("/{post_id}", response_model=PostPublic)
def update_post(post_id: int, data: PostUpdate, db: SessionDep, current_user: CurrentUser):
    post = get_post_or_404(db, post_id)
    require(post.author_id == current_user.id or is_admin(current_user)) #solo el autor puede editar (o un admin)
    post.sqlmodel_update(data.model_dump(exclude_unset=True))
    db.add(post)
    db.commit()
    db.refresh(post)
    return post    


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: SessionDep, current_user: CurrentUser): # mismas reglas que editar.
    post = get_post_or_404(db, post_id)
    require(post.author_id == current_user.id or is_admin(current_user))
    db.delete(post)
    db.commit()
    
    
    