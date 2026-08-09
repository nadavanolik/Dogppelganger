"""Main API endpoints. Mounted at /api."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..model import predict_breed
from ..models import Match
from ..schemas import MatchCreate

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health():
    """Liveness probe used by Docker / the deploy checks."""
    return {"status": "ok"}


@router.post("/match", status_code=201)
def create_match(data: MatchCreate, db: Session = Depends(get_db)):
    """Run the dog-matching model on an uploaded image and store the result."""
    result = predict_breed(data.image)
    match = Match(
        user_id=data.userId,
        breed_name=result["breedName"],
        trait=result["trait"],
        confidence=result["confidence"],
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
