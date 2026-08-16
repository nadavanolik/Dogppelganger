"""Multi-image upload + processing queue. Mounted at /api/uploads.

Uploading turns each valid image into its own queued job (see queue.py for
how jobs get picked up and processed) and hands back immediately — nothing
here waits on the model.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UploadJob

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

# Same volume as app/game/store.py's GAME_DATA_DIR (mounted at /app/data in
# docker-compose.yml), just a different subfolder — no compose change needed.
UPLOAD_DIR = Path(os.getenv("UPLOAD_DATA_DIR", "data/uploads"))

MAX_FILE_BYTES = 10 * 1024 * 1024  # a phone photo fits well inside this
MAX_OWNER_ID = 64

# The client's declared Content-Type is just a hint — sniff the real format
# from the file's own magic bytes so a renamed .exe can't sneak through.
_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)
_EXT_BY_CONTENT_TYPE = {content_type: ext for _, content_type, ext in _MAGIC}


def _sniff(data: bytes) -> str | None:
    for magic, content_type, _ in _MAGIC:
        if data.startswith(magic):
            return content_type
    return None


def _file_path(job: UploadJob) -> Path:
    ext = _EXT_BY_CONTENT_TYPE.get(job.content_type, "")
    return UPLOAD_DIR / f"{job.id}{ext}"


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

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _file_path(job).write_bytes(data)

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
def upload_image(job_id: int, ownerId: str, db: Session = Depends(get_db)):
    job = db.get(UploadJob, job_id)
    if job is None or job.owner_id != _clean_owner_id(ownerId):
        raise HTTPException(404, "No such upload.")
    path = _file_path(job)
    if not path.exists():
        raise HTTPException(404, "Image file is missing.")
    return FileResponse(path, media_type=job.content_type)
