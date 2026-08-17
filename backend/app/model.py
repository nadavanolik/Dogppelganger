"""The dog-matching model — THE MODEL SEAM.

One function, ``match_dog``, turns a stored human photo into a row of
``dog_assets``. Everything downstream — the upload queue, the routers, the
match tables, the frontend — already speaks in dog references and similarity
scores, so **replacing the stub below is the entire next phase.** Nothing else
has to change.

What is here today is deterministic: it hashes the photo's checksum and picks a
real dog out of the corpus. That is not similarity, but it is honest about what
it is, it exercises the whole stack end to end, and the same photo always comes
back with the same dog (which matters for demos).

The plan for the real one — we have **no human/dog training pairs**, so nothing
supervised is available (DATA_STORAGE.md §7):

1. CLIP image embeddings for both species.
2. Species-mean centring before comparing. Raw CLIP cosine between a person and
   a dog is dominated by the "human vs dog" direction, which makes the nearest
   dog very nearly random; subtracting each species' mean removes it.
3. A shared text-attribute space (``ATTRIBUTES`` below) scored by CLIP prompts,
   which is species-invariant *and* gives us a real answer for `shared_traits`
   instead of a bare percentage.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import DogAsset
from .storage.imaging import checksum_of

# The vocabulary both species get scored against. Chosen to be things that can
# sensibly be true of a face of either kind — "fluffy" reads on a person's hair
# and a dog's coat alike, whereas "wet nose" would only ever match one side and
# so carries no matching signal at all.
ATTRIBUTES: tuple[str, ...] = (
    "fluffy",
    "sleepy eyes",
    "long face",
    "round face",
    "serious expression",
    "goofy grin",
    "big ears",
    "shaggy hair",
    "golden colouring",
    "dark colouring",
    "wide eyed",
    "grumpy",
)
ATTRIBUTE_SET = "v1"


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


@dataclass(frozen=True)
class DogMatchResult:
    """What a match produced, in the shape the database columns expect."""

    dog_asset_id: int
    manifest_index: int | None
    slug: str
    score: float
    shared_traits: list[str] = field(default_factory=list)


def _digest(image_path: Path | None, fallback: str | None) -> str:
    """A stable hex digest for whatever we were given to match on."""
    if image_path is not None and image_path.exists():
        return checksum_of(image_path.read_bytes())
    return hashlib.sha256((fallback or "anonymous").encode("utf-8")).hexdigest()


def match_dog(
    db: Session,
    image_path: Path | None = None,
    *,
    fallback_seed: str | None = None,
) -> DogMatchResult:
    """Find the dog this photo looks most like.

    `image_path` is the stored, already-normalised original (see
    app/storage/imaging.py) — the model never sees client-supplied bytes.
    `fallback_seed` covers the legacy ``POST /api/match`` path, which passes a
    string rather than a file.

    Raises `CorpusEmpty` if no dogs have been ingested.
    """
    total = db.query(func.count(DogAsset.id)).scalar() or 0
    if total == 0:
        raise CorpusEmpty()

    digest = _digest(image_path, fallback_seed)

    # PLACEHOLDER selection: an offset into the corpus derived from the photo's
    # own hash. Ordered by id so the same digest always lands on the same dog
    # regardless of insertion order.
    offset = int(digest, 16) % total
    dog = db.query(DogAsset).order_by(DogAsset.id).offset(offset).limit(1).one()

    # PLACEHOLDER explanation: two attributes drawn from the same hash. The
    # real version reads them out of the dog's attribute vector.
    first = int(digest[:8], 16) % len(ATTRIBUTES)
    second = (first + 1 + int(digest[8:16], 16) % (len(ATTRIBUTES) - 1)) % len(ATTRIBUTES)
    traits = [ATTRIBUTES[first], ATTRIBUTES[second]]

    # PLACEHOLDER score, kept in the 0.70-0.99 band a real cosine similarity
    # would plausibly occupy so the UI doesn't need rescaling later.
    score = round(0.70 + (int(digest[16:20], 16) % 30) / 100, 2)

    return DogMatchResult(
        dog_asset_id=dog.id,
        manifest_index=dog.manifest_index,
        slug=dog.slug,
        score=score,
        shared_traits=traits,
    )
