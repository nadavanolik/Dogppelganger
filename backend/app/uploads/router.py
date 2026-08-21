"""Multi-image upload + processing queue. Mounted at /api/uploads.

Uploading turns each valid image into its own queued job (see queue.py for
how jobs get picked up and processed) and hands back immediately — nothing
here waits on the model.

Bytes never land on disk as the client sent them: every accepted image is
decoded and re-encoded by ``app/storage/imaging.py`` first, which is what
strips EXIF/GPS, fixes sideways photos, and neutralises anything hidden in a
metadata segment. See DATA_STORAGE.md §6.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_media_user_optional
from ..models import Comment, Post, Reaction, UploadJob, User
from ..storage import layout
from ..storage.imaging import ImageRejected, decode, write_derivatives

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

MAX_FILE_BYTES = 10 * 1024 * 1024  # a phone photo fits well inside this
# A single request can't be used to fill the disk in one shot. Batches larger
# than this are a queue-fairness problem anyway (see queue.py).
MAX_FILES_PER_REQUEST = 20

# The client's declared Content-Type is just a hint — sniff the real format
# from the file's own magic bytes so a renamed .exe can't sneak through.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

# Which stored derivative each ?size= maps to. "orig" is deliberately absent:
# it is the model's input, and there is no reason to serve a browser 1024px of
# somebody's face when 512 is the largest the UI ever renders.
_SERVABLE = {"display": "image/webp", "thumb": "image/webp"}


def _sniff(data: bytes) -> str | None:
    for magic, content_type in _MAGIC:
        if data.startswith(magic):
            return content_type
    return None


@router.post("", status_code=201)
async def upload_images(
    files: list[UploadFile] = File(...),
    urgent: str = Form("[]"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Queue every valid image in the batch; report the rest as rejected.

    `urgent` is a JSON array of booleans, positionally matched to `files` —
    it's stored on the job today but doesn't affect processing order yet
    (see queue.py's priority_key).

    The photo belongs to whoever holds the token. There used to be an `ownerId`
    form field here that the server took on faith, which meant anyone could
    upload into anyone's account by typing a different string.
    """
    owner_id = user.id
    if not files:
        raise HTTPException(422, "no files were uploaded")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            422, f"too many files at once — send at most {MAX_FILES_PER_REQUEST} per upload"
        )

    try:
        urgent_flags = json.loads(urgent)
        if not isinstance(urgent_flags, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(422, "urgent must be a JSON array of booleans, one per file")

    created: list[dict] = []
    rejected: list[dict] = []

    for i, upload in enumerate(files):
        data = await upload.read()
        content_type = _sniff(data)
        display_name = upload.filename or f"file {i + 1}"

        if content_type is None:
            rejected.append(
                {"filename": display_name, "reason": "not a valid image file — only PNG and JPG are accepted"}
            )
            continue
        if len(data) > MAX_FILE_BYTES:
            rejected.append(
                {"filename": display_name, "reason": f"file is larger than {MAX_FILE_BYTES // (1024 * 1024)}MB"}
            )
            continue

        # Decode before creating the row, so a bomb or a corrupt file leaves no
        # orphan job behind. `ImageRejected` carries a user-safe message.
        #
        # Off the event loop: Pillow is synchronous CPU work, and this handler
        # is async. A 20-file batch would otherwise block the loop for seconds
        # — no WebSocket frames delivered, no progress from the queue workers,
        # every other request stalled behind it.
        try:
            image = await asyncio.to_thread(decode, data)
        except ImageRejected as exc:
            rejected.append({"filename": display_name, "reason": str(exc)})
            continue

        job = UploadJob(
            owner_id=owner_id,
            original_filename=display_name[:255],
            content_type=content_type,
            urgent=bool(urgent_flags[i]) if i < len(urgent_flags) else False,
            status="queued",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # The id is the filename, so the derivatives can only be written once
        # the row exists. If that write fails the row would point at nothing —
        # so drop it and report the file as rejected rather than queue a job
        # the worker is certain to fail on.
        try:
            layout.ensure_upload_dirs(job.id)
            targets = {
                layout.upload_path(job.id, size): spec
                for size, spec in layout.UPLOAD_SIZES.items()
            }
            stored = await asyncio.to_thread(write_derivatives, data, targets, image)
        except (ImageRejected, OSError) as exc:
            layout.delete_upload_files(job.id)
            db.delete(job)
            db.commit()
            rejected.append({"filename": display_name, "reason": f"could not be stored: {exc}"})
            continue

        # Measured after re-encoding, not taken from the multipart headers:
        # byte_size is the queue's shortest-job-first proxy, so it has to
        # describe the file the worker will actually read.
        job.checksum = stored.checksum
        job.byte_size = stored.byte_size
        job.width = stored.width
        job.height = stored.height
        db.commit()
        db.refresh(job)

        created.append(job.as_dict())

    return {"created": created, "rejected": rejected}


@router.get("")
def list_uploads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """My jobs, newest first — the personal queue/results area."""
    rows = (
        db.query(UploadJob)
        .filter(UploadJob.owner_id == user.id)
        .order_by(UploadJob.id.desc())
        .all()
    )
    return [r.as_dict() for r in rows]


@router.get("/{job_id}")
def get_upload(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One job, for the result page.

    Same deliberate conflation of "not yours" with "doesn't exist" as the image
    endpoint: a 403 would confirm the id is real, letting someone probe for
    other people's uploads.
    """
    job = db.get(UploadJob, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(404, "No such upload.")
    return job.as_dict()


def _may_read_image(db: Session, job: UploadJob, viewer: User | None) -> bool:
    """Who can see an uploaded photo.

    Three arms, in order of how public they are:

    1. **Shared to the gallery** — readable by anyone, logged in or not. That
       is not a leak, it is what sharing means; the owner opted in and can
       reverse it. It has to be anonymous because ProjectPlan §2.1 puts a
       featured strip of the gallery on the logged-out landing page.
    2. **The owner** — the obvious one.
    3. **Backs a forum post** — readable by any logged-in user. Without this
       arm every thumbnail in the forum feed would 404, because a post's photo
       belongs to its author, not to the person reading the thread.

    Arm 3 replaces a real bug rather than adding permissiveness: the frontend
    used to fetch these by passing the *author's* id as `ownerId`, so the old
    "ownership check" was defeated by anyone who read the post JSON.
    """
    if job.shared_at is not None:
        return True
    if viewer is None:
        return False
    if job.owner_id == viewer.id:
        return True
    return db.query(Post.id).filter(Post.image_job_id == job.id).first() is not None


@router.get("/{job_id}/image")
def upload_image(
    job_id: int,
    size: str = "display",
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_media_user_optional),
):
    """Serve one uploaded photo, if the caller is allowed to see it.

    Unlike dog photos — which nginx serves straight off a read-only mount —
    user photos are personal data, so every read goes through this check and is
    marked no-store. That is slower, and it is the right trade-off
    (DATA_STORAGE.md §2.2).

    `no-store` also does real work here: it is what makes unsharing a match take
    effect immediately rather than whenever a cache expires.
    """
    if size not in _SERVABLE:
        raise HTTPException(422, f"unknown size {size!r}; expected one of {sorted(_SERVABLE)}")

    job = db.get(UploadJob, job_id)
    if job is None or not _may_read_image(db, job, viewer):
        raise HTTPException(404, "No such upload.")

    path = layout.upload_path(job_id, size)
    media_type = _SERVABLE[size]
    if not path.exists():
        # Volumes seeded by the build before derivatives existed still have the
        # original at the old flat path. Serve it rather than 404 after a deploy.
        legacy = layout.legacy_upload_path(job_id, job.content_type)
        if not legacy.exists():
            raise HTTPException(404, "Image file is missing.")
        path, media_type = legacy, job.content_type

    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, no-store"},
    )


def _own_job(db: Session, job_id: int, user: User) -> UploadJob:
    job = db.get(UploadJob, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(404, "No such upload.")
    return job


@router.post("/{job_id}/share")
def share_upload(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Publish a finished match to the public gallery. Idempotent."""
    job = _own_job(db, job_id, user)
    if job.status != "done" or job.dog_asset_id is None:
        # Sharing a queued or failed job would put an empty card in the
        # gallery, and sharing something that never found a dog would put a
        # photo of a person there with nothing to pair it with.
        raise HTTPException(422, "Only a finished match can be shared.")
    if job.shared_at is None:
        job.shared_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
    return job.as_dict()


@router.delete("/{job_id}/share")
def unshare_upload(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Take a match back out of the gallery. Idempotent.

    Takes effect on the very next request: the access check re-runs against the
    row every time, and the image response is `no-store`, so there is no cached
    copy to outlive the decision.
    """
    job = _own_job(db, job_id, user)
    if job.shared_at is not None:
        job.shared_at = None
        db.commit()
        db.refresh(job)
    return job.as_dict()


@router.delete("/{job_id}", status_code=204)
def delete_upload(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete one upload: its files, its row, and any post that shared it.

    Files first, while the id is still known. The post has to go too — its
    whole content was that photo, and `Post.image_job_id` is unique, so leaving
    it would strand a caption pointing at nothing.
    """
    job = _own_job(db, job_id, user)
    layout.delete_upload_files(job.id, job.content_type)
    post = db.query(Post).filter(Post.image_job_id == job.id).first()
    if post is not None:
        db.query(Comment).filter(Comment.post_id == post.id).delete(synchronize_session=False)
        db.query(Reaction).filter(
            Reaction.target_type == "post", Reaction.target_id == post.id
        ).delete(synchronize_session=False)
        db.delete(post)
    db.delete(job)
    db.commit()
    return None
