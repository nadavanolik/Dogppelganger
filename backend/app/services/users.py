"""Deleting an account.

The rule the user chose: **erase the person, keep the conversation.** Photos,
matches, reactions and every byte on disk go; posts, comments and sent messages
stay, credited to "[deleted user]", because a thread other people replied to
stops making sense with holes punched in it.

Every step is written out explicitly instead of relying on `ondelete=` in the
DDL. That is not belt-and-braces, it is necessary: SQLite does not enforce
foreign keys at all unless `PRAGMA foreign_keys=ON` is issued per connection,
which `app/database.py` never does — so cascades fire in production Postgres and
silently do nothing under pytest. Doing it here means the tests exercise the
same path production takes.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..game import store
from ..models import (
    Comment,
    Conversation,
    Match,
    Message,
    Notification,
    Post,
    Reaction,
    UploadJob,
    User,
)
from ..storage import layout


def delete_user(db: Session, user: User) -> None:
    """Erase a user's personal data and anonymise everything they wrote."""
    user_id = user.id

    # 1. Photos off disk first, while the job ids are still known.
    jobs = db.query(UploadJob).filter(UploadJob.owner_id == user_id).all()
    job_ids = [job.id for job in jobs]
    for job in jobs:
        layout.delete_upload_files(job.id, job.content_type)

    # Posts that shared one of those photos keep their words and lose the
    # picture. This must happen *before* the jobs are deleted: Postgres
    # enforces `posts.image_job_id -> upload_jobs.id` and would refuse the
    # delete, even though SQLite would let it slide and leave a dangling id.
    if job_ids:
        db.query(Post).filter(Post.image_job_id.in_(job_ids)).update(
            {"image_job_id": None}, synchronize_session=False
        )

    # 2. Attachment files on messages this user sent. A video of the sender's
    #    face is their personal data wherever it now sits, so it goes even
    #    though the message row itself survives.
    sent = (
        db.query(Message)
        .filter(Message.sender_id == user_id, Message.attachment_kind.isnot(None))
        .all()
    )
    for message in sent:
        layout.delete_attachment_files(message.id, message.attachment_content_type)
    if sent:
        db.query(Message).filter(
            Message.sender_id == user_id, Message.attachment_kind.isnot(None)
        ).update(
            {
                "attachment_kind": None,
                "attachment_content_type": None,
                "attachment_byte_size": None,
                "attachment_width": None,
                "attachment_height": None,
                "attachment_name": None,
            },
            synchronize_session=False,
        )

    # 3. Rows that are *about* this person and mean nothing without them.
    db.query(Reaction).filter(Reaction.user_id == user_id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Match).filter(Match.user_id == user_id).delete(synchronize_session=False)
    db.query(UploadJob).filter(UploadJob.owner_id == user_id).delete(synchronize_session=False)

    # 4. Rows addressed to other people: keep the content, drop the author.
    db.query(Post).filter(Post.author_id == user_id).update(
        {"author_id": None}, synchronize_session=False
    )
    db.query(Comment).filter(Comment.author_id == user_id).update(
        {"author_id": None}, synchronize_session=False
    )
    db.query(Message).filter(Message.sender_id == user_id).update(
        {"sender_id": None}, synchronize_session=False
    )

    # 5. Conversations. Null this user's side; if the other side is already
    #    gone, nobody can ever read the thread again, so take it with us.
    conversations = (
        db.query(Conversation)
        .filter(
            (Conversation.user_a_id == user_id) | (Conversation.user_b_id == user_id)
        )
        .all()
    )
    for conv in conversations:
        other_id = conv.user_b_id if conv.user_a_id == user_id else conv.user_a_id
        if other_id is None:
            for message in db.query(Message).filter(Message.conversation_id == conv.id).all():
                if message.attachment_kind:
                    layout.delete_attachment_files(
                        message.id, message.attachment_content_type
                    )
            db.query(Message).filter(Message.conversation_id == conv.id).delete(
                synchronize_session=False
            )
            db.delete(conv)
        elif conv.user_a_id == user_id:
            conv.user_a_id = None
        else:
            conv.user_b_id = None

    # 6. The one store that isn't SQL.
    store.forget_player(str(user_id))

    # 7. The row itself — which releases the email and username for reuse,
    #    because there is no tombstone holding them.
    db.delete(user)
    db.commit()
