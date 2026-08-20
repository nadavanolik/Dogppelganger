"""REST endpoints for the forum. Mounted at /api/forum.

Sharing a photo *is* making a post: there's no separate "shared" flag on
UploadJob, just a Post whose ``image_job_id`` points at it (see models.py).
Reaction counts and comment counts are computed at read time rather than
cached on the row — simplest thing that works at this project's scale.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Comment, Post, Reaction, UploadJob, shared_traits_payload

router = APIRouter(prefix="/api/forum", tags=["forum"])

MAX_ID = 64


class PostCreate(BaseModel):
    authorId: str = Field(min_length=1, max_length=MAX_ID)
    authorName: str = Field(default="anon", max_length=80)
    body: str = Field(min_length=1, max_length=2000)
    # One of the author's own finished (status == "done") upload jobs.
    imageJobId: int | None = None


class CommentCreate(BaseModel):
    authorId: str = Field(min_length=1, max_length=MAX_ID)
    authorName: str = Field(default="anon", max_length=80)
    body: str = Field(min_length=1, max_length=1000)


class ReactIn(BaseModel):
    userId: str = Field(min_length=1, max_length=MAX_ID)
    targetType: Literal["post", "comment"]
    targetId: int
    kind: Literal["like", "dislike"]


# ------------------------------------------------------------- serialization


def _reaction_summary(db: Session, target_type: str, target_id: int, viewer_id: str) -> dict:
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


def _comment_dict(db: Session, comment: Comment, viewer_id: str) -> dict:
    return {
        "id": comment.id,
        "postId": comment.post_id,
        "authorId": comment.author_id,
        "authorName": comment.author_name,
        "body": comment.body,
        "createdAt": comment.created_at.isoformat() if comment.created_at else None,
        **_reaction_summary(db, "comment", comment.id, viewer_id),
    }


def _post_dict(db: Session, post: Post, viewer_id: str, *, with_comments: bool = False) -> dict:
    data = {
        "id": post.id,
        "authorId": post.author_id,
        "authorName": post.author_name,
        "body": post.body,
        "image": _image_dict(post.image_job),
        "createdAt": post.created_at.isoformat() if post.created_at else None,
        "commentCount": db.query(Comment).filter_by(post_id=post.id).count(),
        **_reaction_summary(db, "post", post.id, viewer_id),
    }
    if with_comments:
        comments = db.query(Comment).filter_by(post_id=post.id).order_by(Comment.id).all()
        data["comments"] = [_comment_dict(db, c, viewer_id) for c in comments]
    return data


# --------------------------------------------------------------------- posts


@router.get("/shareable")
def shareable_images(ownerId: str, db: Session = Depends(get_db)):
    """The owner's finished dogs that aren't already backing a post."""
    owner_id = ownerId.strip()[:MAX_ID]
    already_shared = {
        p.image_job_id for p in db.query(Post).filter(Post.image_job_id.isnot(None)).all()
    }
    rows = (
        db.query(UploadJob)
        .filter(UploadJob.owner_id == owner_id, UploadJob.status == "done")
        .order_by(UploadJob.id.desc())
        .all()
    )
    return [r.as_dict() for r in rows if r.id not in already_shared]


@router.post("", status_code=201)
def create_post(data: PostCreate, db: Session = Depends(get_db)):
    if data.imageJobId is not None:
        job = db.get(UploadJob, data.imageJobId)
        if job is None:
            raise HTTPException(404, "No such upload.")
        if job.owner_id != data.authorId:
            raise HTTPException(403, "You can only share your own photos.")
        if job.status != "done":
            raise HTTPException(422, "Only a finished dog can be shared.")
        already = db.query(Post).filter_by(image_job_id=job.id).first()
        if already is not None:
            raise HTTPException(409, "That photo has already been shared.")

    post = Post(
        author_id=data.authorId,
        author_name=data.authorName.strip() or "anon",
        body=data.body.strip(),
        image_job_id=data.imageJobId,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_dict(db, post, data.authorId)


@router.get("")
def list_posts(viewerId: str = "", authorId: str = "", limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Post)
    if authorId:
        query = query.filter(Post.author_id == authorId.strip()[:MAX_ID])
    rows = query.order_by(Post.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_post_dict(db, p, viewerId) for p in rows]


@router.get("/{post_id}")
def get_post(post_id: int, viewerId: str = "", db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "That post doesn't exist any more.")
    return _post_dict(db, post, viewerId, with_comments=True)


@router.post("/{post_id}/comments", status_code=201)
def add_comment(post_id: int, data: CommentCreate, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "That post doesn't exist any more.")
    comment = Comment(
        post_id=post_id,
        author_id=data.authorId,
        author_name=data.authorName.strip() or "anon",
        body=data.body.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _comment_dict(db, comment, data.authorId)


@router.post("/react")
def react(data: ReactIn, db: Session = Depends(get_db)):
    if data.targetType == "post":
        exists = db.get(Post, data.targetId) is not None
    else:
        exists = db.get(Comment, data.targetId) is not None
    if not exists:
        raise HTTPException(404, "That doesn't exist any more.")

    existing = (
        db.query(Reaction)
        .filter_by(target_type=data.targetType, target_id=data.targetId, user_id=data.userId)
        .first()
    )
    want_like = data.kind == "like"
    if existing is None:
        db.add(
            Reaction(
                target_type=data.targetType,
                target_id=data.targetId,
                user_id=data.userId,
                is_like=want_like,
            )
        )
    elif existing.is_like == want_like:
        db.delete(existing)  # reacting the same way again clears it
    else:
        existing.is_like = want_like  # like <-> dislike
    db.commit()

    return _reaction_summary(db, data.targetType, data.targetId, data.userId)
