"""Database tables (SQLAlchemy models)."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    username = Column(String(80), unique=True, nullable=False)
    password = Column(String(255), nullable=False)  # bcrypt hash
    created_at = Column(DateTime, default=datetime.utcnow)

    matches = relationship("Match", back_populates="user")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    breed_name = Column(String(120), nullable=False)
    trait = Column(String(200))
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="matches")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "userId": self.user_id,
            "breedName": self.breed_name,
            "trait": self.trait,
            "confidence": self.confidence,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class UploadJob(Base):
    """A queued 'turn this photo into a dog' job (see app/uploads).

    ``owner_id`` is a client-supplied string, not a FK to ``users.id`` — the
    same identity seam as ``app/game`` (see ``PlayerRef`` in game/router.py):
    the SPA's login is still local-only, so it trusts the id the browser
    already made for itself. Swap to a real FK once /api/auth issues tokens
    the SPA actually holds; nothing else about this table needs to change.
    """

    __tablename__ = "upload_jobs"

    id = Column(Integer, primary_key=True)
    owner_id = Column(String(64), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(30), nullable=False)
    urgent = Column(Boolean, default=False, nullable=False)
    # queued -> processing -> done | error
    status = Column(String(20), default="queued", nullable=False)
    breed_name = Column(String(120))
    trait = Column(String(200))
    confidence = Column(Float)
    error = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.original_filename,
            "urgent": self.urgent,
            "status": self.status,
            "breedName": self.breed_name,
            "trait": self.trait,
            "confidence": self.confidence,
            "error": self.error,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
        }


class Post(Base):
    """A forum post (see app/forum). Same ``author_id`` identity seam as
    ``UploadJob.owner_id`` — a client-supplied string, not a real login.

    ``image_job_id`` is how "sharing a dog photo with a caption" works: it
    optionally points at one of the author's own finished ``UploadJob`` rows.
    The unique constraint means a given photo can only ever back one post —
    once shared, it's shared.
    """

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    author_id = Column(String(64), nullable=False, index=True)
    author_name = Column(String(80), nullable=False)
    body = Column(String(2000), nullable=False)
    image_job_id = Column(Integer, ForeignKey("upload_jobs.id"), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    image_job = relationship("UploadJob")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    author_id = Column(String(64), nullable=False, index=True)
    author_name = Column(String(80), nullable=False)
    body = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reaction(Base):
    """A like or dislike on a post or a comment.

    One row per (target, user): flipping like<->dislike updates the row in
    place, and reacting the same way again removes it (an un-react). Posts
    and comments share this one table instead of each getting their own —
    ``target_type`` + ``target_id`` is a manual polymorphic reference rather
    than a second FK column, kept simple on purpose (see app/forum/router.py
    for how it's queried).
    """

    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "user_id", name="uq_reaction_target_user"),
    )

    id = Column(Integer, primary_key=True)
    target_type = Column(String(10), nullable=False)  # "post" | "comment"
    target_id = Column(Integer, nullable=False)
    user_id = Column(String(64), nullable=False)
    is_like = Column(Boolean, nullable=False)
