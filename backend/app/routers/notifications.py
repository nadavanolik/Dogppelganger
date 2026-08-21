"""Bell notifications. Mounted at /api/notifications.

Deliberately **not** used for direct messages. One row per chat message would
double the write volume and create a second unread model competing with
`Message.read_at`; the UI already separates them, with the envelope badge
reading the DM unread total and the bell reading this table.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, User
from ..routers.ws import manager

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _dict(row: Notification) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "text": row.text,
        "href": row.href,
        "read": row.read_at is not None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


async def notify(
    db: Session,
    user_id: int,
    kind: str,
    text: str,
    href: str | None = None,
    *,
    collapse_prefix: str | None = None,
) -> Notification:
    """Create a notification and push it if the recipient is connected.

    Persist first, push second — an offline recipient finds it on next login,
    which is the whole reason it is a row and not just a frame.

    `collapse_prefix` folds repeated news from one person about one thing into
    a single row: an unread notification of the same kind and href whose text
    starts with the prefix is **rewritten** rather than joined by a second.
    Pass the actor's `"@name "`.

    Reactions want this. Liking, un-liking, liking again and then switching to
    a dislike is one piece of news whose *value* changed, not four — and the
    row has to end up saying what they think **now**, so collapsing cannot just
    drop the later news on the floor. Comments pass nothing: a second comment
    really is something new to hear.
    """
    row = None
    if collapse_prefix is not None:
        # The prefix is matched in Python, not with a SQL LIKE: a username may
        # contain `_`, which LIKE reads as a single-character wildcard and
        # would quietly collapse two different people's reactions into one.
        candidates = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.kind == kind,
                Notification.href == href,
                Notification.read_at.is_(None),
            )
            .all()
        )
        row = next((n for n in candidates if n.text.startswith(collapse_prefix)), None)

    if row is None:
        row = Notification(user_id=user_id, kind=kind, text=text[:200], href=href)
        db.add(row)
    else:
        # Same story, new ending. The timestamp moves with it, since what it
        # describes is the reaction they hold now, not the one they started on.
        row.text = text[:200]
        row.created_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    await manager.send_to_user(user_id, {"type": "notification", "payload": _dict(row)})
    return row


@router.get("")
def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(limit)
        .all()
    )
    unread = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .count()
    )
    return {"unread": unread, "items": [_dict(r) for r in rows]}


@router.post("/read")
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .update({"read_at": datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
    return {"markedRead": updated}
