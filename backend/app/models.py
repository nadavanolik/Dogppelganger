"""Database tables (SQLAlchemy models)."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base
from .storage import layout


def shared_traits_payload(raw) -> list[dict]:
    """Normalise the `shared_traits` JSON column for the wire.

    Rows written before traits carried a strength hold plain strings, and they
    are not worth a migration — a match keeps its meaning without the number,
    and rewriting historical rows would mean inventing strengths that were
    never measured. So both shapes are accepted and old rows report
    `strength: null`, which the UI renders as the label alone.
    """
    payload: list[dict] = []
    for item in raw or []:
        if isinstance(item, str):
            payload.append({"label": item, "strength": None})
        elif isinstance(item, dict) and item.get("label"):
            payload.append({"label": item["label"], "strength": item.get("strength")})
    return payload


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    # Indexed as well as unique: the DM user-directory search filters on it
    # with a prefix match, and `unique` alone doesn't promise an index on
    # every backend.
    username = Column(String(80), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)  # bcrypt hash

    # Bumped whenever every existing session must stop working — a password
    # change, today. Tokens carry the value they were minted with, and
    # `deps.get_current_user` rejects any that disagrees with the row.
    #
    # This is the whole answer to "JWTs can't be revoked". Without it a token
    # stolen an hour ago keeps working for its full 24 hours *after* the
    # password it was issued against has been changed, which makes the
    # change-password endpoint decorative.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # No cascade= on these. Deletion is done explicitly and in a specific order
    # by app/services/users.py, because the rules differ per table (erase a
    # photo, anonymise a post) and because SQLite — which the tests run on —
    # does not enforce ondelete at all unless PRAGMA foreign_keys is on. Letting
    # the ORM cascade here would mean the tests and production do different
    # things, and the tests would be the ones lying.
    matches = relationship("Match", back_populates="user")
    uploads = relationship("UploadJob", back_populates="owner")
    posts = relationship("Post", back_populates="author")
    comments = relationship("Comment", back_populates="author")
    reactions = relationship("Reaction", back_populates="user")
    messages_sent = relationship("Message", back_populates="sender")
    notifications = relationship("Notification", back_populates="user")


class DogAsset(Base):
    """One dog photo in the retrieval corpus (AFHQ) — see DATA_STORAGE.md §4.1.

    The row holds *metadata and vectors only*; the pixels live on the `dogdata`
    volume under ``layout.dog_path(slug, size)`` and are served straight off
    disk by nginx. That split is the whole point: 226MB of immutable public
    JPEGs have no business in ``bytea``, where they would bloat every backup
    and every shared-buffer read to replace a job the page cache does better.

    ``slug`` is the identity — it is the filename nginx serves and the key the
    ingest script skips on, so re-running the ingest over the same dataset is a
    no-op. ``checksum`` is the SHA-256 of the source file, deliberately *not*
    unique: AFHQ contains byte-identical photos under different filenames, and
    one duplicate must not abort a 5,239-image run. It is indexed so the ingest
    can report those duplicates, which matter for retrieval — a dog present
    twice is twice as likely to be matched.
    """

    __tablename__ = "dog_assets"

    id = Column(Integer, primary_key=True)
    # Stable public name with no extension, e.g. "flickr_dog_000002".
    slug = Column(String(64), unique=True, nullable=False, index=True)
    checksum = Column(String(64), nullable=False, index=True)
    source_split = Column(String(10))  # "train" | "val" — AFHQ provenance
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    byte_size = Column(Integer, nullable=False)

    # Position in src/lib/dogImages.json. The backend names a dog to the
    # frontend by this integer (see app/game/content.py and src/lib/dogSrc.ts),
    # so it has to stay in lockstep with that file — the ingest script verifies
    # it. Nullable only for the window inside ingest before indices are dealt.
    manifest_index = Column(Integer, unique=True, index=True)

    # float32 vectors as raw bytes (np.ndarray.tobytes()). Portable across
    # SQLite and Postgres, and 10.7MB for the whole corpus at 512 dims, which
    # is small enough to hold in RAM and scan linearly — no index needed.
    # NULL until the embedding pass runs; see DATA_STORAGE.md §4.2.
    embedding = Column(LargeBinary)
    embedding_dim = Column(Integer)
    embedding_model = Column(String(64), index=True)
    # The interpretable side: how strongly this dog reads as each attribute in
    # the vocabulary named by `attribute_set`. Backs `shared_traits` on a match.
    attributes = Column(LargeBinary)
    attribute_set = Column(String(64))

    created_at = Column(DateTime, default=datetime.utcnow)

    def image_url(self, size: str = "256") -> str:
        """The public URL nginx serves this dog from."""
        return f"/dogs/{size}/{layout.dog_filename(self.slug, size)}"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "index": self.manifest_index,
            "width": self.width,
            "height": self.height,
            "thumbUrl": self.image_url("128"),
            "imageUrl": self.image_url("256"),
            "fullUrl": self.image_url("512"),
        }


class Calibration(Base):
    """Human-side population statistics — what makes cross-species comparison work.

    CLIP embeddings are dominated by *what kind of thing* is pictured: every dog
    sits in one tight cluster and every human in another, so a raw cosine
    between a person and a dog is nearly constant and its ranking is noise.
    Subtracting each species' own mean removes that shared direction and leaves
    the within-species variation — unusually fluffy, unusually dark, unusually
    long-faced — which is the axis resemblance actually lives on.

    Only the *human* side is stored. The dog statistics are derived from the
    corpus at load time, so they cannot drift out of step with the vectors they
    describe; the human side has no such source, which is why it is computed
    once from a reference face set (see scripts/calibrate_humans.py).

    ``model`` and ``attribute_set`` are part of the unique key: statistics from
    one encoder are meaningless applied to another's vectors, and a mismatch
    must be detectable rather than silently wrong.
    """

    __tablename__ = "calibrations"
    __table_args__ = (
        UniqueConstraint("species", "model", "attribute_set", name="uq_calibration_space"),
    )

    id = Column(Integer, primary_key=True)
    species = Column(String(10), nullable=False, default="human")
    model = Column(String(64), nullable=False)
    attribute_set = Column(String(64), nullable=False)

    embedding_dim = Column(Integer, nullable=False)
    attribute_dim = Column(Integer, nullable=False)

    # float32 blobs, same convention as DogAsset — see app/ml/vectors.py.
    embedding_mean = Column(LargeBinary, nullable=False)
    attribute_mean = Column(LargeBinary, nullable=False)
    attribute_std = Column(LargeBinary, nullable=False)

    sample_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Match(Base):
    """A completed human -> dog match.

    NOTE: this overlaps heavily with ``UploadJob`` now that both carry a dog
    reference. Collapsing the two is a follow-up for the whole team, not a
    unilateral call — ``/api/match`` is a live endpoint (see routers/views.py).
    """

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    # A match is a private result about one person's face, so it dies with the
    # account rather than being anonymised (contrast Post.author_id).
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Which dog was retrieved. Nullable because a match can exist before the
    # corpus has been ingested (fresh dev database, empty volume).
    dog_asset_id = Column(Integer, ForeignKey("dog_assets.id"), nullable=True)
    # Similarity, 0..1. Named `score` and not `confidence` deliberately: this is
    # retrieval distance, not a classifier's probability of being right.
    score = Column(Float)
    # Why this dog — the attributes the person and the dog scored alike on.
    shared_traits = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="matches")
    dog = relationship("DogAsset")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "userId": self.user_id,
            "dog": self.dog.as_dict() if self.dog else None,
            "dogIndex": self.dog.manifest_index if self.dog else None,
            "score": self.score,
            "sharedTraits": shared_traits_payload(self.shared_traits),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class UploadJob(Base):
    """A queued 'turn this photo into a dog' job (see app/uploads).

    ``owner_id`` is a real foreign key: the photo belongs to whoever was
    holding the token that uploaded it, and the server never takes the client's
    word for who that is. It cascades on delete because an uploaded photo *is*
    personal data — DATA_STORAGE.md §6's retention rule says its bytes live
    exactly as long as this row.
    """

    __tablename__ = "upload_jobs"
    __table_args__ = (
        # Covers the public gallery's "recently shared, newest first" scan.
        Index("ix_upload_jobs_gallery", "shared_at", "id"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(30), nullable=False)
    urgent = Column(Boolean, default=False, nullable=False)
    # queued -> processing -> done | error
    status = Column(String(20), default="queued", nullable=False)

    # What we actually stored, measured after re-encoding rather than taken
    # from the multipart headers. `byte_size` is the queue's shortest-job-first
    # proxy (see uploads/queue.py), so a client-supplied number won't do.
    checksum = Column(String(64), index=True)
    byte_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)

    # The result: which dog, how close, and why.
    dog_asset_id = Column(Integer, ForeignKey("dog_assets.id"), nullable=True)
    score = Column(Float)
    shared_traits = Column(JSON)

    error = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    # When the owner published this match to the public gallery. NULL means
    # private, which is the default — nothing is public unless someone says so.
    #
    # A nullable timestamp rather than a `shared` boolean: a bool plus a
    # `shared_at` would be two columns for one fact that can contradict each
    # other, and the timestamp answers "is it shared" (IS NOT NULL) *and* gives
    # the gallery its sort key. A photo uploaded last week and shared today
    # belongs at the top of "recently shared", which created_at cannot express.
    shared_at = Column(DateTime, nullable=True, index=True)

    owner = relationship("User", back_populates="uploads")
    dog = relationship("DogAsset")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.original_filename,
            "urgent": self.urgent,
            "status": self.status,
            "shared": self.shared_at is not None,
            "sharedAt": self.shared_at.isoformat() if self.shared_at else None,
            "byteSize": self.byte_size,
            "width": self.width,
            "height": self.height,
            "dog": self.dog.as_dict() if self.dog else None,
            "dogIndex": self.dog.manifest_index if self.dog else None,
            "score": self.score,
            "sharedTraits": shared_traits_payload(self.shared_traits),
            "error": self.error,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
        }


class Post(Base):
    """A forum post (see app/forum).

    ``author_id`` is **nullable on purpose**. Deleting an account anonymises
    what that person wrote rather than deleting it, because a thread other
    people replied to stops making sense with holes in it. The author then
    reads as "[deleted user]" — see ``app/serialization.py``.

    There is no ``author_name`` column any more. It was a denormalised snapshot
    that existed only because there was no user row to join to; with a real FK
    the username lives in exactly one place, so a rename follows every post the
    author ever made.

    ``image_job_id`` is how "sharing a dog photo with a caption" works: it
    optionally points at one of the author's own finished ``UploadJob`` rows.
    The unique constraint means a given photo can only ever back one post —
    once shared, it's shared. It is ``SET NULL`` rather than ``CASCADE``
    because upload jobs *do* die with their owner: an anonymised post keeps its
    words and loses its photo, which is exactly the intended outcome.
    """

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    author_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body = Column(String(2000), nullable=False)
    image_job_id = Column(
        Integer,
        ForeignKey("upload_jobs.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    author = relationship("User", back_populates="posts")
    image_job = relationship("UploadJob")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable for the same reason as Post.author_id — see that docstring.
    author_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    author = relationship("User", back_populates="comments")


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
    # Cascades rather than anonymising, unlike posts and comments. Two reasons:
    # a reaction records what one specific person liked, which is exactly the
    # personal data a deletion is meant to erase; and a NULL here would defeat
    # the unique constraint below, since NULLs don't collide — one ghost could
    # then accumulate unlimited likes on a single post.
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_like = Column(Boolean, nullable=False)

    user = relationship("User", back_populates="reactions")


class Conversation(Base):
    """A 1:1 direct-message thread.

    Two tables rather than one. The obvious alternative — a single ``messages``
    table with ``sender_id``/``recipient_id``, where "the conversation" is just
    the unordered pair — falls over on the inbox query, which needs the latest
    message per pair. Grouping on an unordered pair means ``LEAST``/``GREATEST``
    on Postgres and ``MIN``/``MAX`` on SQLite: *different function names*, in the
    one query that has to be right, across the exact split this project runs
    (tests on SQLite, production on Postgres). A conversation row also gives
    ``/messages/:id`` a stable integer id, which the SPA route already assumes.

    ``user_a_id < user_b_id`` is an invariant, enforced both by the CHECK below
    and by ``get_or_create`` in app/dm/service.py. It is what makes the unique
    constraint mean "one thread per pair" instead of "one thread per direction".

    The participant columns are **nullable**, and that is forced rather than
    chosen: deleting an account anonymises what the person wrote, so if these
    were NOT NULL the delete would have to remove the conversation and take the
    *other* person's messages with it. Two consequences, both accepted:
    ``uq_conversation_pair`` stops preventing duplicates once a side is NULL
    (harmless — get_or_create only ever looks up two live ids, and a NULL side
    can never be re-paired), and the CHECK still passes because a comparison
    against NULL is NULL, which both engines treat as satisfied.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),
        CheckConstraint("user_a_id < user_b_id", name="ck_conversation_ordered"),
    )

    id = Column(Integer, primary_key=True)
    user_a_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_b_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    # Denormalised so the inbox sorts without a correlated subquery per row.
    # Written in the same transaction as the message insert.
    last_message_at = Column(DateTime, index=True)

    user_a = relationship("User", foreign_keys=[user_a_id])
    user_b = relationship("User", foreign_keys=[user_b_id])

    def other_than(self, user_id: int):
        """The participant who isn't ``user_id`` — may be None if deleted."""
        return self.user_b if self.user_a_id == user_id else self.user_a

    def involves(self, user_id: int) -> bool:
        return user_id in (self.user_a_id, self.user_b_id)


class Message(Base):
    """One direct message, optionally carrying a single image or video.

    Ordering and pagination are by ``id``, never ``created_at``: two messages
    written in the same tick share a timestamp, and an ordering that can tie is
    an ordering that can lose a message off the end of a page. The id is
    monotonic, so ``?before=<id>`` is a stable cursor.

    ``read_at`` is per-message rather than a per-participant high-water mark on
    the conversation. It is one nullable column instead of two, it stays correct
    when the same person has two tabs open, and the inbox's unread counts are
    one grouped query. The high-water-mark design is O(1) to update instead of
    O(unread) and is the right answer at scale; this project does not have that
    scale and the simpler thing is easier to get right.

    The attachment lives in columns rather than its own table because a message
    carries at most one — the composer is a single file input — so a 1:1 table
    whose rows are always created and destroyed with their parent would be a
    join pretending to be a decision. There is deliberately **no path column**:
    the path is a pure function of ``(id, attachment_content_type)``, the same
    principle ``UploadJob`` and ``DogAsset.slug`` already follow, so the row and
    the disk cannot disagree.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_history", "conversation_id", "id"),
        Index("ix_messages_unread", "conversation_id", "read_at"),
        # A message must say something or carry something.
        CheckConstraint(
            "body IS NOT NULL OR attachment_kind IS NOT NULL", name="ck_message_not_empty"
        ),
    )

    id = Column(Integer, primary_key=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Nullable because an attachment with no caption is the common case, and
    # "" would make "no caption" and "a caption of spaces" indistinguishable
    # after stripping.
    body = Column(String(2000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)

    attachment_kind = Column(String(5), nullable=True)  # "image" | "video"
    # What *we* decided to serve after sniffing the bytes, never the header the
    # client sent.
    attachment_content_type = Column(String(40), nullable=True)
    attachment_byte_size = Column(Integer, nullable=True)
    attachment_width = Column(Integer, nullable=True)  # images only
    attachment_height = Column(Integer, nullable=True)
    # The user's original filename, for display only. Never used to build a
    # path — that would hand the caller control of where bytes land.
    attachment_name = Column(String(255), nullable=True)

    sender = relationship("User", back_populates="messages_sent")
    conversation = relationship("Conversation")


class Notification(Base):
    """An in-app alert for one person.

    Deliberately **not** written for direct messages. One row per chat message
    would double the write volume and create a second unread model competing
    with ``Message.read_at``. The UI already splits them: the envelope badge
    reads the DM unread total, the bell reads this table.
    """

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(20), nullable=False)  # "match" | "reaction" | "comment"
    text = Column(String(200), nullable=False)
    href = Column(String(200), nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="notifications")

