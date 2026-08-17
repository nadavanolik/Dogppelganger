"""Retrieval: given a photo of a person, find the dog they most resemble.

The whole approach exists to work around one constraint — **there are no
human/dog training pairs**, so nothing supervised is available. Everything here
is zero-shot on top of CLIP, and the two corrections below are what make it
work at all rather than returning an effectively random dog.

**1. Species-mean centring.** Subtract the mean dog vector from every dog and
the mean human vector from every human before comparing. Raw CLIP cosine
between a person and a dog is dominated by "is a dog" versus "is a person",
which is a constant offset carrying no information about resemblance; what is
left after centring is how each face differs from its own kind, and *that* is
comparable across species.

**2. A shared attribute space.** Score both species against the same sixteen
text prompts (`app/ml/attributes.py`) and compare those scores instead. It is
species-neutral by construction, and it is the only part of the pipeline that
can say *why* — the traits the person and the dog both score unusually high on.

The two are blended. The embedding side is richer but noisier; the attribute
side is coarse but interpretable and much harder to fool.

Retrieval is a plain matrix multiply. 5,239 × 512 float32 is 10.7MB, which sits
in RAM and scans in about a millisecond — an index would be slower than the
scan it replaces at this size.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ..models import Calibration, DogAsset
from . import attributes as attrs
from .encoder import EMBEDDING_DIM, MODEL_NAME, ClipImageEncoder
from .faces import FaceCropper
from .vectors import l2_normalize, unpack

# How much of the score comes from the raw centred embedding versus the
# attribute space. Even weighting: the embedding captures more, the attributes
# generalise better across the species gap, and neither is trustworthy alone.
EMBEDDING_WEIGHT = float(os.getenv("MATCH_EMBEDDING_WEIGHT", "0.5"))

# Guards a divide-by-zero for an attribute with no spread in the reference set.
EPSILON = 1e-6

# How many traits to show as the reason for a match.
MAX_SHARED_TRAITS = 3


class NotCalibrated(RuntimeError):
    """The corpus has no embeddings, or there are no human statistics yet."""


@dataclass(frozen=True)
class DogCandidate:
    dog_asset_id: int
    manifest_index: int | None
    slug: str
    score: float
    shared_traits: list[str] = field(default_factory=list)


class DogMatcher:
    """Holds the corpus in memory. Build once; it is read-only afterwards."""

    def __init__(
        self,
        *,
        dog_ids: np.ndarray,
        dog_indices: list[int | None],
        dog_slugs: list[str],
        dog_embeddings: np.ndarray,  # (N, 512) unit vectors
        dog_attributes: np.ndarray,  # (N, K) raw prompt similarities
        human_embedding_mean: np.ndarray,  # (512,)
        human_attribute_mean: np.ndarray,  # (K,)
        human_attribute_std: np.ndarray,  # (K,)
        text_vectors: np.ndarray,  # (K, 512) unit vectors
        encoder: ClipImageEncoder,
        cropper: FaceCropper,
    ) -> None:
        self._ids = dog_ids
        self._indices = dog_indices
        self._slugs = dog_slugs
        self._text = text_vectors
        self._encoder = encoder
        self._cropper = cropper

        self._human_embedding_mean = human_embedding_mean
        self._human_attribute_mean = human_attribute_mean
        self._human_attribute_std = np.maximum(human_attribute_std, EPSILON)

        # Dog-side statistics come from the corpus itself rather than storage,
        # so they can never describe a different set of vectors than the ones
        # they are applied to.
        self._centred_dogs = l2_normalize(dog_embeddings - dog_embeddings.mean(axis=0))

        attribute_mean = dog_attributes.mean(axis=0)
        attribute_std = np.maximum(dog_attributes.std(axis=0), EPSILON)
        # z-scored per attribute: raw prompt similarities have wildly different
        # baselines ("dark colouring" scores high on almost every dog), and
        # without this the strong-baseline attributes would drown the rest.
        self._dog_attribute_z = (dog_attributes - attribute_mean) / attribute_std
        self._dog_attribute_unit = l2_normalize(self._dog_attribute_z)

    # ------------------------------------------------------------- building

    @classmethod
    def build(
        cls,
        db: Session,
        *,
        encoder: ClipImageEncoder | None = None,
        cropper: FaceCropper | None = None,
    ) -> "DogMatcher":
        """Load the corpus and calibration out of the database.

        `encoder` and `cropper` are injectable so a caller can supply an
        already-warmed instance instead of parsing a 350MB graph again — and so
        tests can drive the arithmetic with a 6KB stand-in graph rather than
        shipping CLIP into CI.
        """
        rows = (
            db.query(DogAsset)
            .filter(DogAsset.embedding.isnot(None))
            .filter(DogAsset.embedding_model == MODEL_NAME)
            .filter(DogAsset.attribute_set == attrs.ATTRIBUTE_SET)
            .order_by(DogAsset.id)
            .all()
        )
        if not rows:
            raise NotCalibrated(
                "no dogs have been embedded yet — run scripts/embed_dogs.py "
                "(see DATA_STORAGE.md §7)"
            )

        calibration = (
            db.query(Calibration)
            .filter_by(species="human", model=MODEL_NAME, attribute_set=attrs.ATTRIBUTE_SET)
            .one_or_none()
        )
        if calibration is None:
            raise NotCalibrated(
                "no human calibration for this model — run scripts/calibrate_humans.py "
                "(see DATA_STORAGE.md §7)"
            )

        return cls(
            dog_ids=np.array([r.id for r in rows], dtype=np.int64),
            dog_indices=[r.manifest_index for r in rows],
            dog_slugs=[r.slug for r in rows],
            dog_embeddings=np.stack([unpack(r.embedding, EMBEDDING_DIM) for r in rows]),
            dog_attributes=np.stack([unpack(r.attributes, attrs.DIM) for r in rows]),
            human_embedding_mean=unpack(calibration.embedding_mean, EMBEDDING_DIM),
            human_attribute_mean=unpack(calibration.attribute_mean, attrs.DIM),
            human_attribute_std=unpack(calibration.attribute_std, attrs.DIM),
            text_vectors=load_text_vectors(),
            encoder=encoder or ClipImageEncoder(),
            cropper=cropper or FaceCropper(),
        )

    # ------------------------------------------------------------- matching

    def attribute_scores(self, embedding: np.ndarray) -> np.ndarray:
        """How strongly one unit embedding reads as each attribute."""
        return self._text @ embedding

    def match(self, image: Image.Image) -> DogCandidate:
        """The closest dog to this photo. Raises `NoFaceFound` if there isn't a face."""
        face = self._cropper.crop(image)
        embedding = self._encoder.encode(face)
        return self.match_embedding(embedding)

    def match_embedding(self, embedding: np.ndarray) -> DogCandidate:
        """The same, starting from an already-encoded unit vector."""
        centred = l2_normalize(embedding - self._human_embedding_mean)
        embedding_similarity = self._centred_dogs @ centred

        raw = self.attribute_scores(embedding)
        human_z = (raw - self._human_attribute_mean) / self._human_attribute_std
        attribute_similarity = self._dog_attribute_unit @ l2_normalize(human_z)

        combined = (
            EMBEDDING_WEIGHT * embedding_similarity
            + (1.0 - EMBEDDING_WEIGHT) * attribute_similarity
        )
        winner = int(np.argmax(combined))

        return DogCandidate(
            dog_asset_id=int(self._ids[winner]),
            manifest_index=self._indices[winner],
            slug=self._slugs[winner],
            score=_distinctiveness(combined, winner),
            shared_traits=self._shared_traits(human_z, winner),
        )

    def _shared_traits(self, human_z: np.ndarray, winner: int) -> list[str]:
        """The attributes this person and this dog are *both* unusually high on.

        `min` of the two z-scores, not the product or the sum: an attribute only
        counts as shared if neither side is merely average, and a product would
        let two strong negatives ("both unusually un-fluffy") masquerade as
        agreement.
        """
        agreement = np.minimum(human_z, self._dog_attribute_z[winner])
        ranked = np.argsort(agreement)[::-1][:MAX_SHARED_TRAITS]
        return [attrs.LABELS[k] for k in ranked if agreement[k] > 0]


def _distinctiveness(scores: np.ndarray, winner: int) -> float:
    """Turn the winning similarity into something meaningful to show a user.

    The raw cosine is unhelpful on its own — after centring it lands in a narrow
    band, so "0.19" says nothing. What a reader actually wants to know is how
    far this dog stands out from the other 5,238, so we report where the winner
    sits in the corpus's own distribution, squashed to 0-1.

    This is a distinctiveness measure, not a probability: a high number means
    "this dog is a much better fit than the rest", not "97% likely correct".
    """
    spread = float(scores.std())
    if spread < EPSILON:
        return 0.5
    z = (float(scores[winner]) - float(scores.mean())) / spread
    return round(float(1.0 / (1.0 + np.exp(-z / 2.0))), 3)


def load_text_vectors() -> np.ndarray:
    """The baked attribute prompt embeddings (scripts/export_encoder.py)."""
    from pathlib import Path

    path = Path(__file__).parent / "assets" / f"attribute_text_{attrs.ATTRIBUTE_SET}.npy"
    if not path.exists():
        raise NotCalibrated(
            f"the attribute prompt embeddings are missing at {path} — "
            "run `python scripts/export_encoder.py`"
        )
    vectors = np.load(path).astype(np.float32)
    if vectors.shape != (attrs.DIM, EMBEDDING_DIM):
        raise NotCalibrated(
            f"{path} holds {vectors.shape} but attribute set "
            f"{attrs.ATTRIBUTE_SET!r} needs {(attrs.DIM, EMBEDDING_DIM)} — "
            "the vocabulary changed without re-running the export"
        )
    return vectors


# ------------------------------------------------------------------ caching

_matcher: DogMatcher | None = None
_lock = threading.Lock()


def get_matcher(db: Session) -> DogMatcher:
    """Process-wide matcher, built on first use.

    Locked because the upload workers call this from a thread pool, and
    building it twice would parse a 350MB graph twice for no reason.
    """
    global _matcher
    if _matcher is None:
        with _lock:
            if _matcher is None:
                _matcher = DogMatcher.build(db)
    return _matcher


def reset() -> None:
    """Drop the cached matcher — after re-embedding, and between tests."""
    global _matcher
    with _lock:
        _matcher = None
