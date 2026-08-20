#!/usr/bin/env python
"""Compute the human-side statistics the matcher needs. Run once per model.

    # Labeled Faces in the Wild — the standard academic face benchmark, ~180MB.
    # Mirrored on figshare; the original UMass host no longer resolves.
    curl -L -o lfw.tgz https://ndownloader.figshare.com/files/5976018
    tar xzf lfw.tgz
    python scripts/calibrate_humans.py --source ./lfw

**What this is for.** Matching subtracts each species' own mean before
comparing, because a raw CLIP cosine between a person and a dog mostly measures
"person versus dog" and ranks the corpus by noise. The dog mean comes free from
the corpus. The human mean has no such source — AFHQ contains cats, dogs and
wild animals and no people — so it is computed here, once, from a reference set
of faces, and stored in ``calibrations``.

Any directory of face photos works; LFW is simply a convenient, freely
available, well-known one. The images are read and thrown away: nothing is
copied into the repository or the database except the aggregate statistics, so
there is no dataset to redistribute and no face is retained.

**Faces go through the same crop and preprocessing as an upload.** That is the
whole point — statistics gathered on differently-framed images would be applied
to photos framed another way, and the correction would be measuring the
difference in framing as much as anything else.
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
from app.ml.encoder import EMBEDDING_DIM, MODEL_NAME, ClipImageEncoder  # noqa: E402
from app.ml.faces import FaceCropper, NoFaceFound  # noqa: E402
from app.ml.matcher import load_text_vectors  # noqa: E402
from app.ml.vectors import pack  # noqa: E402
from app.models import Calibration  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# A few hundred faces already pin a 512-d mean down well; the standard error
# falls with sqrt(n), so going past this buys precision nobody can perceive
# while making the pass take much longer.
DEFAULT_LIMIT = 1500
BATCH_SIZE = 32

# Below this the statistics are too noisy to be worth applying, and a bad
# correction is worse than none — it would tilt every match the same way.
MIN_SAMPLES = 50


def collect(source: Path, limit: int) -> list[Path]:
    if not source.is_dir():
        raise SystemExit(f"--source {source} is not a directory")
    found = [p for p in sorted(source.rglob("*")) if p.suffix.lower() in IMAGE_SUFFIXES]
    if not found:
        raise SystemExit(f"no images found under {source}")
    # Evenly spaced rather than the first N: LFW is sorted by person, so the
    # first 1500 files would be a few hundred individuals photographed
    # repeatedly instead of a cross-section of faces.
    if len(found) > limit:
        step = len(found) / limit
        found = [found[int(i * step)] for i in range(limit)]
    return found


def calibrate(
    source: Path,
    limit: int = DEFAULT_LIMIT,
    batch_size: int = BATCH_SIZE,
    encoder: ClipImageEncoder | None = None,
    cropper=None,
    min_samples: int = MIN_SAMPLES,
):
    """Returns (used, skipped). `encoder`/`cropper` are injectable for tests."""
    Base.metadata.create_all(bind=engine)

    encoder = encoder or ClipImageEncoder()
    cropper = cropper or FaceCropper()
    text_vectors = load_text_vectors()

    paths = collect(source, limit)
    print(f"{len(paths)} reference faces to process")

    embeddings: list[np.ndarray] = []
    skipped = 0

    for start in range(0, len(paths), batch_size):
        faces: list[Image.Image] = []
        for path in paths[start : start + batch_size]:
            try:
                with Image.open(path) as handle:
                    faces.append(cropper.crop(handle.convert("RGB")))
            except (NoFaceFound, OSError):
                skipped += 1
        if faces:
            embeddings.append(encoder.encode_images(faces))
        if start and start % (batch_size * 10) == 0:
            print(f"  … {start}/{len(paths)}")

    if not embeddings:
        raise SystemExit("no usable faces — is --source really a folder of face photos?")

    matrix = np.concatenate(embeddings, axis=0)
    if matrix.shape[0] < min_samples:
        raise SystemExit(
            f"only {matrix.shape[0]} usable faces, need at least {min_samples} — "
            "statistics this noisy would tilt every match the same way"
        )

    attribute_scores = matrix @ text_vectors.T

    db = SessionLocal()
    try:
        row = (
            db.query(Calibration)
            .filter_by(species="human", model=MODEL_NAME, attribute_set=attrs.ATTRIBUTE_SET)
            .one_or_none()
        )
        if row is None:
            row = Calibration(
                species="human", model=MODEL_NAME, attribute_set=attrs.ATTRIBUTE_SET
            )
            db.add(row)

        row.embedding_dim = EMBEDDING_DIM
        row.attribute_dim = attrs.DIM
        row.embedding_mean = pack(matrix.mean(axis=0))
        row.attribute_mean = pack(attribute_scores.mean(axis=0))
        row.attribute_std = pack(attribute_scores.std(axis=0))
        row.sample_count = int(matrix.shape[0])
        db.commit()
    finally:
        db.close()

    return matrix.shape[0], skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="a directory of human face photos")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    used, skipped = calibrate(args.source, args.limit, args.batch_size)
    print(f"\ncalibrated on {used} faces · {skipped} skipped (no face found or unreadable)")
    print(f"stored for {MODEL_NAME} / attribute set {attrs.ATTRIBUTE_SET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
