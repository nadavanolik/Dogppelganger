#!/usr/bin/env python
"""Fill in the dog corpus's CLIP vectors. Run after ingest_dogs.py.

    python scripts/embed_dogs.py

Reads the 512px derivative of every ingested dog and writes two vectors per
row: the CLIP image embedding, and how strongly the dog reads as each of the
attributes in ``app/ml/attributes.py``.

Uses the exported ONNX encoder, not PyTorch — so it needs nothing beyond the
container's own dependencies and can be run on the VM exactly like the ingest.
That is also the point: dogs and uploaded photos then go through byte-identical
preprocessing and the same graph, so the vectors are actually comparable.

Idempotent. Rows already embedded by this model and attribute set are skipped
unless ``--force`` is given; change the vocabulary and everything is redone,
because a corpus half in one attribute space and half in another is worse than
no corpus at all.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.ml import attributes as attrs  # noqa: E402
from app.ml.encoder import MODEL_NAME, ClipImageEncoder  # noqa: E402
from app.ml.matcher import load_text_vectors  # noqa: E402
from app.ml.vectors import pack  # noqa: E402
from app.models import DogAsset  # noqa: E402
from app.storage import layout  # noqa: E402

BATCH_SIZE = 32


def embed(
    force: bool = False,
    batch_size: int = BATCH_SIZE,
    limit: int | None = None,
    encoder: ClipImageEncoder | None = None,
) -> tuple[int, list[str]]:
    """Returns (embedded, errors). `encoder` is injectable so tests can use a
    small stand-in graph instead of loading 350MB."""
    Base.metadata.create_all(bind=engine)

    encoder = encoder or ClipImageEncoder()
    text_vectors = load_text_vectors()

    db = SessionLocal()
    try:
        query = db.query(DogAsset).order_by(DogAsset.id)
        if not force:
            # Anything embedded by a *different* model or vocabulary counts as
            # pending: mixing two vector spaces in one matrix is silently wrong.
            query = query.filter(
                (DogAsset.embedding.is_(None))
                | (DogAsset.embedding_model != MODEL_NAME)
                | (DogAsset.attribute_set != attrs.ATTRIBUTE_SET)
            )
        pending = query.limit(limit).all() if limit else query.all()

        total = db.query(DogAsset).count()
        print(f"{total} dogs in the corpus · {len(pending)} to embed")
        if not pending:
            return 0, []

        done = 0
        errors: list[str] = []
        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            images: list[Image.Image] = []
            usable: list[DogAsset] = []

            for dog in chunk:
                path = layout.dog_path(dog.slug, "512")
                try:
                    with Image.open(path) as handle:
                        images.append(handle.convert("RGB"))
                    usable.append(dog)
                except OSError as exc:
                    errors.append(f"{dog.slug}: {exc}")

            if not usable:
                continue

            # AFHQ photos are already tight head crops, so no face detection
            # here — running a *human* face detector over dog faces would
            # reject most of the corpus.
            embeddings = encoder.encode_images(images)
            scores = embeddings @ text_vectors.T

            for dog, embedding, attribute_row in zip(usable, embeddings, scores):
                dog.embedding = pack(embedding)
                dog.embedding_dim = int(embedding.shape[0])
                dog.embedding_model = MODEL_NAME
                dog.attributes = pack(attribute_row)
                dog.attribute_set = attrs.ATTRIBUTE_SET
                done += 1

            db.commit()
            print(f"  … {done}/{len(pending)}")

        return done, errors
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-embed dogs that already have vectors")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--limit", type=int, help="only do the first N (for a smoke test)")
    args = parser.parse_args()

    done, errors = embed(args.force, args.batch_size, args.limit)

    print(f"\nembedded {done} · failed {len(errors)}")
    for line in errors[:20]:
        print(f"  ! {line}")

    db = SessionLocal()
    try:
        ready = (
            db.query(DogAsset)
            .filter(DogAsset.embedding.isnot(None), DogAsset.embedding_model == MODEL_NAME)
            .count()
        )
        print(f"corpus now holds {ready} embedded dogs ({MODEL_NAME}, {attrs.ATTRIBUTE_SET})")
    finally:
        db.close()
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
