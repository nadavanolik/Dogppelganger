"""The dog-matching model — THE MODEL SEAM.

One function, ``match_dog``, turns a human photo into a row of ``dog_assets``.
Everything downstream — the upload queue, the routers, the match tables, the
frontend — speaks in dog references and similarity scores, so this is the only
place that knows how matching actually happens.

The mechanics live in ``app/ml``: face detection and cropping (``faces``), the
CLIP image encoder under onnxruntime (``encoder``), the shared attribute
vocabulary (``attributes``), and the retrieval itself (``matcher``). Read
``matcher``'s docstring for why raw CLIP similarity does not work here and what
is done about it.

This module is the thin, boring part: check the preconditions, hand the pixels
over, translate the result into the shape the database columns want.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session

from .ml import matcher as ml_matcher
from .ml.attributes import ATTRIBUTE_SET, LABELS as ATTRIBUTES  # noqa: F401  (re-exported)
from .ml.faces import NoFaceFound  # noqa: F401  (re-exported for the callers that catch it)
from .ml.matcher import NotCalibrated  # noqa: F401  (same)
from .models import DogAsset


class CorpusEmpty(RuntimeError):
    """No dogs are ingested, so there is nothing to match against.

    Raised rather than returning an empty match so the failure surfaces on the
    job with an actionable message instead of showing the user a blank card.
    """

    def __init__(self) -> None:
        super().__init__(
            "The dog corpus is empty — run backend/scripts/ingest_dogs.py "
            "(see DATA_STORAGE.md §5) before matching."
        )


class SourceImageMissing(RuntimeError):
    """We were asked to match a stored photo that isn't on disk.

    Raised rather than quietly matching something else. A job whose derivatives
    were never written — the process died between committing the row and
    writing the files — must look like a failure, not like a successful match.
    """

    def __init__(self, image_path: Path) -> None:
        super().__init__(f"the stored photo is missing at {image_path}")


@dataclass(frozen=True)
class DogMatchResult:
    """What a match produced, in the shape the database columns expect."""

    dog_asset_id: int
    manifest_index: int | None
    slug: str
    score: float
    shared_traits: list[dict] = field(default_factory=list)


def match_dog(
    db: Session,
    image_path: Path | None = None,
    *,
    image: Image.Image | None = None,
) -> DogMatchResult:
    """Find the dog this face looks most like.

    Pass `image_path` for a stored, already-normalised upload (the queue's
    path — the model never sees client-supplied bytes), or `image` for pixels
    already in hand.

    Raises:
        CorpusEmpty: nothing has been ingested.
        NotCalibrated: ingested but not embedded, or no human statistics yet.
        SourceImageMissing: `image_path` was given but isn't on disk.
        NoFaceFound: there is no face in the photo to match.
    """
    if image is None and image_path is None:
        raise ValueError("match_dog needs either an image or a path to one")

    # Checked before the matcher is built, so a fresh install gets "run the
    # ingest" rather than a confusing complaint about missing vectors.
    if (db.query(func.count(DogAsset.id)).scalar() or 0) == 0:
        raise CorpusEmpty()

    if image is None:
        if not image_path.exists():
            raise SourceImageMissing(image_path)
        with Image.open(image_path) as handle:
            image = handle.convert("RGB")

    candidate = ml_matcher.get_matcher(db).match(image)
    return DogMatchResult(
        dog_asset_id=candidate.dog_asset_id,
        manifest_index=candidate.manifest_index,
        slug=candidate.slug,
        score=candidate.score,
        shared_traits=candidate.shared_traits,
    )
