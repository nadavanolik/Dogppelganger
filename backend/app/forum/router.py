"""REST endpoints for the forum. Mounted at /api/forum.

Attaching a photo to a post is one of the two ways a picture becomes visible to
other people; the other is sharing a match to the gallery
(``UploadJob.shared_at``, see app/routers/gallery.py). They are independent:
a post can carry a photo that was never shared to the gallery, and a shared
match needs no caption.

Reaction counts and comment counts are computed at read time rather than cached
on the row — simplest thing that works at this project's scale.

Every endpoint here identifies the caller from their token. There used to be
``authorId``/``viewerId``/``userId`` fields in the bodies and query strings,
which meant anyone could post, comment or vote as anyone else by typing a
different string.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_current_user
from ..models import Comment, Post, Reaction, UploadJob, User, shared_traits_payload
from ..serialization import author_ref

router = APIRouter(prefix="/api/forum", tags=["forum"])


class PostCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    # One of the author's own finished (status == "done") upload jobs.
    imageJobId: int | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class ReactIn(BaseModel):
    targetType: Literal["post", "comment"]
    targetId: int
    kind: Literal["like", "dislike"]


# ------------------------------------------------------------- serialization


def _reaction_summary(db: Session, target_type: str, target_id: int, viewer_id: int | None) -> dict:
    rows = db.query(Reaction).filter_by(target_type=target_type, target_id=target_id).all()
    likes = sum(1 for r in rows if r.is_like)
    dislikes = sum(1 for r in rows if not r.is_like)
    mine = next((r.is_like for r in rows if viewer_id and r.user_id == viewer_id), None)
    my_reaction = "like" if mine is True else "dislike" if mine is False else None
    return {"likeCount": likes, "dislikeCount": dislikes, "myReaction": my_reaction}


def _image_dict(job: UploadJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "jobId": job.id,
        "dog": job.dog.as_dict() if job.dog else None,
        "dogIndex": job.dog.manifest_index if job.dog else None,
        "score": job.score,
        "sharedTraits": shared_traits_payload(job.shared_traits),
    }


def _comment_dict(db: Session, comment: Comment, viewer_id: int | None) -> dict:
    author = author_ref(comment.author)
    return {
        "id": comment.id,
        "postId": comment.post_id,
        "authorId": author["id"],
        "authorName": author["username"],
        "body": comment.body,
        "createdAt": comment.created_at.isoformat() if comment.created_at else None,
        **_reaction_summary(db, "comment", comment.id, viewer_id),
    }


def _post_dict(db: Session, post: Post, viewer_id: int | None, *, with_comments: bool = False) -> dict:
    author = author_ref(post.author)
    data = {
        "id": post.id,
        # Null when the author deleted their account. `authorName` is never
        # null — see app/serialization.py for the contract.
        "authorId": author["id"],
        "authorName": author["username"],
        "body": post.body,
        "image": _image_dict(post.image_job),
        "createdAt": post.created_at.isoformat() if post.created_at else None,
        "commentCount": db.query(Comment).filter_by(post_id=post.id).count(),
        **_reaction_summary(db, "post", post.id, viewer_id),
    }
    if with_comments:
        comments = (
            db.query(Comment)
            .options(joinedload(Comment.author))
            .filter_by(post_id=post.id)
            .order_by(Comment.id)
            .all()
        )
        data["comments"] = [_comment_dict(db, c, viewer_id) for c in comments]
    return data


# --------------------------------------------------------------------- posts


@router.get("/shareable")
def shareable_images(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """My finished dogs that aren't already backing a post."""
    already_shared = {
        p.image_job_id for p in db.query(Post).filter(Post.image_job_id.isnot(None)).all()
    }
    rows = (
        db.query(UploadJob)
        .filter(UploadJob.owner_id == user.id, UploadJob.status == "done")
        .order_by(UploadJob.id.desc())
        .all()
    )
    return [r.as_dict() for r in rows if r.id not in already_shared]


@router.post("", status_code=201)
def create_post(
    data: PostCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.imageJobId is not None:
        job = db.get(UploadJob, data.imageJobId)
        if job is None:
            raise HTTPException(404, "No such upload.")
        if job.owner_id != user.id:
            # 403 rather than the 404 used elsewhere, and deliberately so: you
            # picked this id out of your own list, so its existence is not a
            # secret being leaked to you.
            raise HTTPException(403, "You can only share your own photos.")
        if job.status != "done":
            raise HTTPException(422, "Only a finished dog can be shared.")
        already = db.query(Post).filter_by(image_job_id=job.id).first()
        if already is not None:
            raise HTTPException(409, "That photo has already been shared.")

    post = Post(author_id=user.id, body=data.body.strip(), image_job_id=data.imageJobId)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_dict(db, post, user.id)


@router.get("")
def list_posts(
    authorId: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Post).options(joinedload(Post.author), joinedload(Post.image_job))
    if authorId is not None:
        query = query.filter(Post.author_id == authorId)
    rows = query.order_by(Post.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_post_dict(db, p, user.id) for p in rows]


@router.get("/{post_id}")
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "That post doesn't exist any more.")
    return _post_dict(db, post, user.id, with_comments=True)


@router.post("/{post_id}/comments", status_code=201)
def add_comment(
    post_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "That post doesn't exist any more.")
    comment = Comment(post_id=post_id, author_id=user.id, body=data.body.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _comment_dict(db, comment, user.id)


def _drop_reactions(db: Session, target_type: str, target_id: int) -> None:
    """Reactions are a manual polymorphic reference, so nothing cascades them."""
    db.query(Reaction).filter_by(target_type=target_type, target_id=target_id).delete(
        synchronize_session=False
    )


# Declared before `/{post_id}`: FastAPI matches routes in definition order, and
# `post_id` is typed `int`, so the other way round `DELETE /comments/5` would hit
# that route with post_id="comments" and 422 instead of falling through.
@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete your own comment. The thread around it is untouched."""
    comment = db.get(Comment, comment_id)
    if comment is None or comment.author_id != user.id:
        raise HTTPException(404, "That comment doesn't exist any more.")

    _drop_reactions(db, "comment", comment.id)
    db.delete(comment)
    db.commit()
    return None


@router.delete("/{post_id}", status_code=204)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete your own post, its comments and every reaction to them.

    404 rather than 403 when it isn't yours, matching the rest of the app.

    The photo survives. `image_job_id` points at an upload the author still
    owns, and "I regret the caption" is not "delete my photo" — it goes back to
    being an unshared match on their profile, ready to post again.
    """
    post = db.get(Post, post_id)
    if post is None or post.author_id != user.id:
        raise HTTPException(404, "That post doesn't exist any more.")

    for comment in db.query(Comment).filter_by(post_id=post.id).all():
        _drop_reactions(db, "comment", comment.id)
    db.query(Comment).filter_by(post_id=post.id).delete(synchronize_session=False)
    _drop_reactions(db, "post", post.id)
    db.delete(post)
    db.commit()
    return None


@router.post("/react")
def react(
    data: ReactIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.targetType == "post":
        exists = db.get(Post, data.targetId) is not None
    else:
        exists = db.get(Comment, data.targetId) is not None
    if not exists:
        raise HTTPException(404, "That doesn't exist any more.")

    existing = (
        db.query(Reaction)
        .filter_by(target_type=data.targetType, target_id=data.targetId, user_id=user.id)
        .first()
    )
    want_like = data.kind == "like"
    if existing is None:
        db.add(
            Reaction(
                target_type=data.targetType,
                target_id=data.targetId,
                user_id=user.id,
                is_like=want_like,
            )
        )
    elif existing.is_like == want_like:
        db.delete(existing)  # reacting the same way again clears it
    else:
        existing.is_like = want_like  # like <-> dislike
    db.commit()

    return _reaction_summary(db, data.targetType, data.targetId, user.id)
