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

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UploadJob
from ..storage import layout
from ..storage.imaging import ImageRejected, decode, write_derivatives

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

MAX_FILE_BYTES = 10 * 1024 * 1024  # a phone photo fits well inside this
# A single request can't be used to fill the disk in one shot. Batches larger
# than this are a queue-fairness problem anyway (see queue.py).
MAX_FILES_PER_REQUEST = 20
MAX_OWNER_ID = 64

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


def _clean_owner_id(owner_id: str) -> str:
    return owner_id.strip()[:MAX_OWNER_ID]


@router.post("", status_code=201)
async def upload_images(
    ownerId: str = Form(...),
    files: list[UploadFile] = File(...),
    urgent: str = Form("[]"),
    db: Session = Depends(get_db),
):
    """Queue every valid image in the batch; report the rest as rejected.

    `urgent` is a JSON array of booleans, positionally matched to `files` —
    it's stored on the job today but doesn't affect processing order yet
    (see queue.py's priority_key).
    """
    owner_id = _clean_owner_id(ownerId)
    if not owner_id:
        raise HTTPException(422, "ownerId is required")
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
        try:
            image = decode(data)
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
            stored = write_derivatives(data, targets, image=image)
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
def list_uploads(ownerId: str, db: Session = Depends(get_db)):
    """An owner's jobs, newest first — their personal queue/results area."""
    rows = (
        db.query(UploadJob)
        .filter(UploadJob.owner_id == _clean_owner_id(ownerId))
        .order_by(UploadJob.id.desc())
        .all()
    )
    return [r.as_dict() for r in rows]


@router.get("/{job_id}/image")
def upload_image(job_id: int, ownerId: str, size: str = "display", db: Session = Depends(get_db)):
    """Serve one of an owner's uploaded photos.

    Unlike dog photos — which nginx serves straight off a read-only mount —
    user photos are personal data, so every read goes through this ownership
    check and is marked no-store. That is slower, and it is the right
    trade-off (DATA_STORAGE.md §2.2).
    """
    if size not in _SERVABLE:
        raise HTTPException(422, f"unknown size {size!r}; expected one of {sorted(_SERVABLE)}")

    job = db.get(UploadJob, job_id)
    if job is None or job.owner_id != _clean_owner_id(ownerId):
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
