"""Read-only view of the dog corpus. Mounted at /api/dogs.

Deliberately *not* an image endpoint: the pixels are public and immutable, so
nginx serves them straight off the read-only `dogdata` mount and never troubles
Python (DATA_STORAGE.md §2.2). What's here is the metadata a caller can't get
from a URL — how many dogs exist, whether they've been embedded yet, and the
index/slug mapping the frontend relies on.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DogAsset

router = APIRouter(prefix="/api/dogs", tags=["dogs"])


@router.get("/stats")
def corpus_stats(db: Session = Depends(get_db)):
    """Is the corpus ingested, and is it embedded?

    Worth hitting after a deploy: `total: 0` means the volume is empty and
    every match will fail, which is otherwise only visible one broken card at
    a time.
    """
    total = db.query(func.count(DogAsset.id)).scalar() or 0
    embedded = (
        db.query(func.count(DogAsset.id)).filter(DogAsset.embedding.isnot(None)).scalar() or 0
    )
    model = (
        db.query(DogAsset.embedding_model)
        .filter(DogAsset.embedding_model.isnot(None))
        .limit(1)
        .scalar()
    )
    return {"total": total, "embedded": embedded, "embeddingModel": model}


@router.get("/manifest")
def manifest(db: Session = Depends(get_db)):
    """The corpus ordering as the database has it: slugs, sorted.

    This is what `src/lib/dogImages.json` must equal. The ingest script checks
    it, but having it over HTTP means the drift can be diagnosed on a running
    VM without shelling in.
    """
    slugs = [slug for (slug,) in db.query(DogAsset.slug).order_by(DogAsset.slug).all()]
    return {"count": len(slugs), "slugs": slugs}


@router.get("/{index}")
def dog_by_index(index: int, db: Session = Depends(get_db)):
    """One dog's metadata by its manifest index — the id used on the wire."""
    dog = db.query(DogAsset).filter(DogAsset.manifest_index == index).one_or_none()
    if dog is None:
        raise HTTPException(404, "No such dog.")
    return dog.as_dict()
