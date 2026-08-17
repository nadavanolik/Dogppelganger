"""Main API endpoints. Mounted at /api."""
import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..model import CorpusEmpty, NoFaceFound, NotCalibrated, match_dog
from ..models import Match
from ..schemas import MatchCreate
from ..storage.imaging import ImageRejected, decode

# Base64 inflates by ~4/3, so this caps the decoded image at roughly the same
# 10MB the multipart upload path allows.
MAX_PAYLOAD_CHARS = 14 * 1024 * 1024

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health():
    """Liveness probe used by Docker / the deploy checks."""
    return {"status": "ok"}


def _decode_payload(payload: str) -> bytes:
    """A base64 image, with or without a `data:image/...;base64,` prefix."""
    if len(payload) > MAX_PAYLOAD_CHARS:
        raise HTTPException(413, "that image is too large — send at most 10MB")
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "image must be base64, optionally as a data URL") from None


@router.post("/match", status_code=201)
def create_match(data: MatchCreate, db: Session = Depends(get_db)):
    """Match one photo synchronously and store the result.

    The batch path in app/uploads is the main one — it stores the photo, queues
    the work and pushes the answer over the WebSocket. This endpoint exists for
    a caller that wants a single answer inline and has no file to keep, so it
    takes the image in the request body and stores only the outcome.
    """
    if not data.image:
        raise HTTPException(422, "image is required — send a base64-encoded png or jpg")

    try:
        image = decode(_decode_payload(data.image))
    except ImageRejected as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        result = match_dog(db, image=image)
    except NoFaceFound as exc:
        raise HTTPException(422, str(exc)) from exc
    except (CorpusEmpty, NotCalibrated) as exc:
        # 503, not 500: the service is fine, it just has nothing to match
        # against until someone runs the ingest / embedding passes.
        raise HTTPException(503, str(exc)) from exc

    match = Match(
        user_id=data.userId,
        dog_asset_id=result.dog_asset_id,
        score=result.score,
        shared_traits=result.shared_traits,
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match.as_dict()


@router.get("/matches")
def list_matches(db: Session = Depends(get_db)):
    """Return recent matches (newest first)."""
    rows = db.query(Match).order_by(Match.created_at.desc()).limit(50).all()
    return [m.as_dict() for m in rows]
