"""The public gallery: matches their owners chose to share. Mounted at /api/gallery.

Deliberately **not** "every post that has a picture". The gallery shows
human-to-dog matches, which is a different thing from the forum: a post can
carry a photo without being a match, and a match can be shared without anyone
wanting to write a caption about it. Sharing is its own act, recorded by
`UploadJob.shared_at`.

Anonymous by design. ProjectPlan §2.6 marks `/gallery` as an authenticated page,
but §2.1 puts a featured strip of it on the PUBLIC landing page and specifies
that endpoint as "no auth" — so the data has to be readable logged-out, and the
page can still sit behind a guard if the frontend wants it to.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import UploadJob, shared_traits_payload
from ..serialization import author_ref

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

MAX_LIMIT = 60


def _item(job: UploadJob) -> dict:
    return {
        "jobId": job.id,
        # No media token: a shared match is readable by anyone, which is the
        # whole point of having shared it.
        "imageUrl": f"/api/uploads/{job.id}/image?size=display",
        "thumbUrl": f"/api/uploads/{job.id}/image?size=thumb",
        "owner": author_ref(job.owner),
        "dog": job.dog.as_dict() if job.dog else None,
        "dogIndex": job.dog.manifest_index if job.dog else None,
        "score": job.score,
        "sharedTraits": shared_traits_payload(job.shared_traits),
        "sharedAt": job.shared_at.isoformat() if job.shared_at else None,
    }


def _shared_query(db: Session):
    """Only finished matches that actually found a dog.

    All three conditions matter. A queued job has no result yet, an errored one
    never will, and `dog_asset_id` can be NULL even on a "done" job if the
    corpus was empty when it ran — each would render as a broken card.
    """
    return (
        db.query(UploadJob)
        .options(joinedload(UploadJob.owner), joinedload(UploadJob.dog))
        .filter(
            UploadJob.shared_at.isnot(None),
            UploadJob.status == "done",
            UploadJob.dog_asset_id.isnot(None),
        )
    )


@router.get("")
def list_gallery(
    limit: int = Query(default=24, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Shared matches, most recently shared first.

    Offset paging rather than a cursor, unlike the DM history. That is a
    considered split, not an inconsistency: a gallery is browsed page by page
    and tolerates a row shifting between pages, whereas chat history grows at
    the head, where offsets would skip and repeat messages.
    """
    total = _shared_query(db).count()
    rows = (
        _shared_query(db)
        .order_by(UploadJob.shared_at.desc(), UploadJob.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": [_item(job) for job in rows]}


@router.get("/featured")
def featured(
    limit: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """A short strip for the landing page. Same rules, fewer rows."""
    rows = (
        _shared_query(db)
        .order_by(UploadJob.shared_at.desc(), UploadJob.id.desc())
        .limit(limit)
        .all()
    )
    return [_item(job) for job in rows]
