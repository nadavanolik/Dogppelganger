"""Conversation lookup, unread counting, and the wire shapes for DMs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Conversation, Message, User
from ..serialization import author_ref


def get_or_create_conversation(db: Session, a_id: int, b_id: int) -> Conversation:
    """The thread between two people, creating it the first time.

    The pair is normalised so that the smaller id is always ``user_a_id``. That
    single line is what makes the unique constraint mean "one thread per pair"
    rather than "one per direction" — without it, A messaging B and B messaging
    A would build two separate threads that each show half the conversation.
    """
    low, high = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    conv = (
        db.query(Conversation)
        .filter(Conversation.user_a_id == low, Conversation.user_b_id == high)
        .first()
    )
    if conv is None:
        conv = Conversation(user_a_id=low, user_b_id=high)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def unread_counts(db: Session, conversation_ids: list[int], viewer_id: int) -> dict[int, int]:
    """Unread totals for many conversations in one grouped query.

    One query for the whole inbox rather than one per row — served by
    ``ix_messages_unread``. "Unread" means: not written by me, and never marked
    read.
    """
    if not conversation_ids:
        return {}
    rows = (
        db.query(Message.conversation_id, func.count(Message.id))
        .filter(
            Message.conversation_id.in_(conversation_ids),
            Message.sender_id != viewer_id,
            Message.read_at.is_(None),
        )
        .group_by(Message.conversation_id)
        .all()
    )
    return {conversation_id: count for conversation_id, count in rows}


def attachment_dict(message: Message) -> dict | None:
    if not message.attachment_kind:
        return None
    return {
        "kind": message.attachment_kind,
        "contentType": message.attachment_content_type,
        "byteSize": message.attachment_byte_size,
        "width": message.attachment_width,
        "height": message.attachment_height,
        "name": message.attachment_name,
        "url": f"/api/dm/messages/{message.id}/attachment",
        # Only images have derivatives; a video is served whole.
        "thumbUrl": (
            f"/api/dm/messages/{message.id}/attachment?size=thumb"
            if message.attachment_kind == "image"
            else None
        ),
    }


def message_dict(message: Message, viewer_id: int) -> dict:
    sender = author_ref(message.sender)
    return {
        "id": message.id,
        "conversationId": message.conversation_id,
        "senderId": sender["id"],
        "senderName": sender["username"],
        # An id comparison, never a name one: two deleted accounts would both
        # be called "[deleted user]".
        "mine": message.sender_id == viewer_id,
        "body": message.body,
        "attachment": attachment_dict(message),
        "createdAt": message.created_at.isoformat() if message.created_at else None,
        "readAt": message.read_at.isoformat() if message.read_at else None,
    }


def conversation_dict(
    db: Session,
    conv: Conversation,
    viewer_id: int,
    *,
    unread: int = 0,
    last: Message | None = None,
) -> dict:
    other: User | None = conv.other_than(viewer_id)
    return {
        "id": conv.id,
        "other": author_ref(other),
        # The other participant may have deleted their account. The history
        # stays readable; there is just nobody left to reply to. Saying so
        # explicitly saves the client inferring it from a null id.
        "canReply": other is not None,
        "unreadCount": unread,
        "lastMessage": message_dict(last, viewer_id) if last is not None else None,
        "lastMessageAt": (
            conv.last_message_at.isoformat() if conv.last_message_at else None
        ),
    }


def touch(conv: Conversation, when: datetime | None = None) -> None:
    """Bump the denormalised inbox sort key, in the same transaction as the insert."""
    conv.last_message_at = when or datetime.utcnow()
