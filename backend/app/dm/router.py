"""REST endpoints for direct messages. Mounted at /api/dm."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_current_user, get_media_user
from ..models import Conversation, Message, User
from ..routers.ws import manager
from ..storage import layout
from ..storage.imaging import ImageRejected, decode, write_derivatives
from .attachments import AttachmentRejected, read_validated, store_video
from .service import (
    conversation_dict,
    get_or_create_conversation,
    message_dict,
    touch,
    unread_counts,
)

router = APIRouter(prefix="/api/dm", tags=["dm"])

MAX_BODY = 2000
DEFAULT_PAGE = 50


class StartConversation(BaseModel):
    userId: int


def _conversation_or_404(db: Session, conversation_id: int, user: User) -> Conversation:
    """A conversation the caller is in, or 404.

    404 rather than 403 for someone else's thread, the same rule the upload
    endpoints use: a 403 would confirm the id is real, which is all you need to
    find out who is talking to whom.
    """
    conv = db.get(Conversation, conversation_id)
    if conv is None or not conv.involves(user.id):
        raise HTTPException(404, "No such conversation.")
    return conv


# ------------------------------------------------------------- conversations


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The inbox: every thread, most recently active first."""
    convs = (
        db.query(Conversation)
        .options(joinedload(Conversation.user_a), joinedload(Conversation.user_b))
        .filter((Conversation.user_a_id == user.id) | (Conversation.user_b_id == user.id))
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
        .all()
    )
    counts = unread_counts(db, [c.id for c in convs], user.id)
    out = []
    for conv in convs:
        last = (
            db.query(Message)
            .options(joinedload(Message.sender))
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .first()
        )
        out.append(
            conversation_dict(db, conv, user.id, unread=counts.get(conv.id, 0), last=last)
        )
    return out


@router.post("/conversations", status_code=201)
def start_conversation(
    data: StartConversation,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Open (or reopen) the thread with someone. Idempotent."""
    if data.userId == user.id:
        raise HTTPException(422, "You can't message yourself.")
    other = db.get(User, data.userId)
    if other is None:
        raise HTTPException(404, "No such user.")
    conv = get_or_create_conversation(db, user.id, other.id)
    return conversation_dict(db, conv, user.id)


# ------------------------------------------------------------------ messages


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    before: int | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """A page of history, newest first.

    Paged by id rather than by offset: history grows at the head, so an offset
    would skip and repeat messages as new ones arrive mid-scroll. `?before=<id>`
    is stable no matter what happens while you are reading.
    """
    conv = _conversation_or_404(db, conversation_id, user)
    query = (
        db.query(Message)
        .options(joinedload(Message.sender))
        .filter(Message.conversation_id == conv.id)
    )
    if before is not None:
        query = query.filter(Message.id < before)
    rows = query.order_by(Message.id.desc()).limit(limit).all()
    return {
        "messages": [message_dict(m, user.id) for m in rows],
        "hasMore": len(rows) == limit,
    }


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_message(
    conversation_id: int,
    body: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send a message, optionally carrying one image or video.

    Persist first, push second — always in that order. A message is a row before
    it is ever a frame, which is what makes the history complete even if the
    recipient's socket was down when it was sent.

    `async def` with the (indexed, fast) SQLAlchemy calls inline, because the
    push is a coroutine on the app's event loop. The genuinely slow part —
    Pillow decoding a phone photo — goes to a thread. `app/uploads/router.py`
    already does exactly this.
    """
    conv = _conversation_or_404(db, conversation_id, user)
    text = body.strip()
    has_file = file is not None and file.filename

    if not text and not has_file:
        raise HTTPException(422, "A message needs some text or an attachment.")
    if len(text) > MAX_BODY:
        raise HTTPException(422, f"A message can be at most {MAX_BODY} characters.")

    content_type = data = temp_path = image = kind = None
    if has_file:
        try:
            content_type, data, temp_path = await read_validated(file)
        except AttachmentRejected as exc:
            raise HTTPException(422, str(exc)) from exc
        kind, _ = layout.ATTACHMENT_TYPES[content_type]
        if kind == "image":
            # Decode before the row exists, so a corrupt file leaves no orphan
            # message behind — same order as the upload path.
            try:
                image = await asyncio.to_thread(decode, data)
            except ImageRejected as exc:
                raise HTTPException(422, str(exc)) from exc

    message = Message(
        conversation_id=conv.id,
        sender_id=user.id,
        body=text or None,
        # Set now, not after the bytes land: an attachment-only message has no
        # body, and `ck_message_not_empty` would reject the insert otherwise.
        attachment_kind=kind,
        attachment_name=(file.filename[:255] if has_file else None),
    )
    db.add(message)
    touch(conv)
    db.commit()
    db.refresh(message)

    if has_file:
        # The id is the filename, so the bytes can only be written once the row
        # exists. If that fails, drop the row rather than leave a message
        # pointing at a file that was never written.
        try:
            if kind == "image":
                layout.ensure_attachment_dirs(message.id)
                targets = {
                    layout.attachment_derivative_path(message.id, size): spec
                    for size, spec in layout.ATTACHMENT_SIZES.items()
                }
                stored = await asyncio.to_thread(write_derivatives, data, targets, image)
                # The "original" for an image is the display derivative: no ML
                # runs on a DM photo, so a full-resolution copy is pure disk.
                message.attachment_content_type = "image/webp"
                message.attachment_byte_size = stored.byte_size
                message.attachment_width = stored.width
                message.attachment_height = stored.height
            else:
                size = await asyncio.to_thread(
                    store_video, message.id, content_type, temp_path
                )
                message.attachment_content_type = content_type
                message.attachment_byte_size = size
            db.commit()
            db.refresh(message)
        except (ImageRejected, OSError, ValueError) as exc:
            layout.delete_attachment_files(message.id, content_type)
            db.delete(message)
            db.commit()
            raise HTTPException(422, f"That attachment could not be stored: {exc}") from exc

    payload = message_dict(message, user.id)
    other = conv.other_than(user.id)
    if other is not None:
        # `mine` is computed per viewer, so the recipient gets their own shape.
        await manager.send_to_user(
            other.id, {"type": "dm_received", "payload": message_dict(message, other.id)}
        )
    # The sender's *other* tabs, so a message typed on a phone appears on the
    # laptop too.
    await manager.send_to_user(user.id, {"type": "dm_sent", "payload": payload})
    return payload


@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark everything the other person sent as read."""
    conv = _conversation_or_404(db, conversation_id, user)
    now = datetime.utcnow()
    updated = (
        db.query(Message)
        .filter(
            Message.conversation_id == conv.id,
            Message.sender_id != user.id,
            Message.read_at.is_(None),
        )
        .update({"read_at": now}, synchronize_session=False)
    )
    db.commit()

    other = conv.other_than(user.id)
    if updated and other is not None:
        await manager.send_to_user(
            other.id,
            {"type": "dm_read", "payload": {"conversationId": conv.id, "readAt": now.isoformat()}},
        )
    return {"conversationId": conv.id, "markedRead": updated}


@router.delete("/messages/{message_id}", status_code=204)
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Unsend one of your own messages, and erase its attachment."""
    message = db.get(Message, message_id)
    if message is None or message.sender_id != user.id:
        raise HTTPException(404, "No such message.")
    if message.attachment_kind:
        layout.delete_attachment_files(message.id, message.attachment_content_type)
    db.delete(message)
    db.commit()
    return None


@router.get("/messages/{message_id}/attachment")
def get_attachment(
    message_id: int,
    size: str = Query(default="display"),
    db: Session = Depends(get_db),
    viewer: User = Depends(get_media_user),
):
    """Serve an attachment to either participant.

    `FileResponse` handles HTTP Range for us — Starlette parses `Range` and
    `If-Range`, answers 206 with `Content-Range`, and 416 when unsatisfiable.
    That is what makes a video scrub instead of having to download whole, so
    this deliberately does **not** wrap the file in a StreamingResponse.
    """
    message = db.get(Message, message_id)
    if message is None or not message.attachment_kind:
        raise HTTPException(404, "No such attachment.")
    conv = db.get(Conversation, message.conversation_id)
    if conv is None or not conv.involves(viewer.id):
        raise HTTPException(404, "No such attachment.")

    if message.attachment_kind == "image":
        if size not in layout.ATTACHMENT_SIZES:
            raise HTTPException(
                422, f"unknown size {size!r}; expected one of {sorted(layout.ATTACHMENT_SIZES)}"
            )
        path = layout.attachment_derivative_path(message.id, size)
        media_type = "image/webp"
    else:
        # `size` is meaningless for video; ignore it rather than 422, so the
        # client doesn't have to branch on kind to build a URL.
        path = layout.attachment_path(message.id, message.attachment_content_type)
        media_type = message.attachment_content_type

    if not path.exists():
        raise HTTPException(404, "Attachment file is missing.")

    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            # We chose this content type from our own allowlist; tell the
            # browser not to second-guess it.
            "X-Content-Type-Options": "nosniff",
        },
    )
