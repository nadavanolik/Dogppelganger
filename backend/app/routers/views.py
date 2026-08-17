"""Main API endpoints. Mounted at /api."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..model import CorpusEmpty, match_dog
from ..models import Match
from ..schemas import MatchCreate

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health():
    """Liveness probe used by Docker / the deploy checks."""
    return {"status": "ok"}


@router.post("/match", status_code=201)
def create_match(data: MatchCreate, db: Session = Depends(get_db)):
    """Run the dog-matching model on an image payload and store the result.

    The batch path in app/uploads is the real one — it stores the photo, queues
    the work and pushes the answer over the WebSocket. This endpoint stays for
    a caller that just wants one synchronous match and has no file to store, so
    it matches on the payload string rather than on stored pixels.
    """
    try:
        result = match_dog(db, fallback_seed=data.image)
    except CorpusEmpty as exc:
        # 503, not 500: the service is fine, it just has nothing to match
        # against until someone runs the ingest.
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
