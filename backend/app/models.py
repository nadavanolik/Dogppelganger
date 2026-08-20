"""Database tables (SQLAlchemy models)."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
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
    username = Column(String(80), unique=True, nullable=False)
    password = Column(String(255), nullable=False)  # bcrypt hash
    created_at = Column(DateTime, default=datetime.utcnow)

    matches = relationship("Match", back_populates="user")


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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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

    dog = relationship("DogAsset")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.original_filename,
            "urgent": self.urgent,
            "status": self.status,
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
