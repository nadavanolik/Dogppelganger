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
from ..routers.notifications import notify
from ..routers.ws import manager
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


# ------------------------------------------------------------- live updates
#
# Every write below persists first and pushes second, the same order the DMs
# and `notify()` follow: the row is the truth, the frame is a courtesy. A
# socket that was flapping costs someone a live update, never the content.


async def _broadcast(event_type: str, payload: dict) -> None:
    """Push a forum change to every connected client.

    `broadcast`, not `send_to_user`: the forum is readable by everyone signed
    in, unlike a DM with its two participants.
    """
    await manager.broadcast({"type": event_type, "payload": payload})


async def _notify_author(
    db: Session,
    author_id: int | None,
    actor: User,
    kind: str,
    text: str,
    href: str,
    *,
    collapse_unread: bool,
) -> None:
    """Tell a post or comment's author what just happened to it.

    Two things are never worth a notification: your own doing, and news for an
    author who no longer exists — `author_id` is nullable because deleting an
    account anonymises what it wrote rather than removing it, see
    app/serialization.py.
    """
    if author_id is None or author_id == actor.id:
        return
    await notify(db, author_id, kind, text, href, collapse_unread=collapse_unread)


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
async def create_post(
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

    # Serialized with viewer_id=None. `myReaction` is computed per viewer, so
    # one broadcast body has to be true for everyone — and null is genuinely
    # true here: nobody has reacted to a post that did not exist a moment ago.
    # That also makes it identical to the author's own view, so one dict does
    # for both the push and the response.
    payload = _post_dict(db, post, None)
    await _broadcast("forum_post", payload)
    return payload


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
async def add_comment(
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

    # viewer_id=None for the same reason as a new post — see create_post.
    payload = _comment_dict(db, comment, None)
    await _broadcast("forum_comment", payload)
    # Not collapsed: a second comment is genuinely something new to hear about,
    # unlike a like that was toggled off and on again.
    await _notify_author(
        db,
        post.author_id,
        user,
        "comment",
        f"@{user.username} commented on your post",
        f"/forum/{post.id}",
        collapse_unread=False,
    )
    return payload


def _drop_reactions(db: Session, target_type: str, target_id: int) -> None:
    """Reactions are a manual polymorphic reference, so nothing cascades them."""
    db.query(Reaction).filter_by(target_type=target_type, target_id=target_id).delete(
        synchronize_session=False
    )


# Declared before `/{post_id}`: FastAPI matches routes in definition order, and
# `post_id` is typed `int`, so the other way round `DELETE /comments/5` would hit
# that route with post_id="comments" and 422 instead of falling through.
@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete your own comment. The thread around it is untouched."""
    comment = db.get(Comment, comment_id)
    if comment is None or comment.author_id != user.id:
        raise HTTPException(404, "That comment doesn't exist any more.")

    # Read the thread it belonged to before the delete — the instance is
    # expired afterwards, and the frame has to say which post to update.
    post_id = comment.post_id
    _drop_reactions(db, "comment", comment.id)
    db.delete(comment)
    db.commit()

    await _broadcast("forum_comment_deleted", {"id": comment_id, "postId": post_id})
    return None


@router.delete("/{post_id}", status_code=204)
async def delete_post(
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

    await _broadcast("forum_post_deleted", {"id": post_id})
    return None


@router.post("/react")
async def react(
    data: ReactIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # The row itself, not just whether it exists: whoever wrote it is the one
    # to notify, and a comment carries the post its href has to point at.
    if data.targetType == "post":
        target = db.get(Post, data.targetId)
    else:
        target = db.get(Comment, data.targetId)
    if target is None:
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
        reacted = True
    elif existing.is_like == want_like:
        db.delete(existing)  # reacting the same way again clears it
        reacted = False
    else:
        existing.is_like = want_like  # like <-> dislike
        reacted = True
    db.commit()

    summary = _reaction_summary(db, data.targetType, data.targetId, user.id)

    # Counts only. `myReaction` in this summary belongs to whoever just
    # clicked, so broadcasting it would light up everyone else's button as
    # though they had reacted. Each client merges the counts and keeps its own.
    await _broadcast(
        "forum_reaction",
        {
            "targetType": data.targetType,
            "targetId": data.targetId,
            "likeCount": summary["likeCount"],
            "dislikeCount": summary["dislikeCount"],
        },
    )

    # Only when a reaction was added or flipped. Taking one back is not news,
    # and notifying on it would make like -> unlike -> like ring three times.
    if reacted:
        verb = "liked" if want_like else "disliked"
        noun = "post" if data.targetType == "post" else "comment"
        post_id = target.id if data.targetType == "post" else target.post_id
        await _notify_author(
            db,
            target.author_id,
            user,
            "reaction",
            f"@{user.username} {verb} your {noun}",
            f"/forum/{post_id}",
            collapse_unread=True,
        )

    return summary
