#!/usr/bin/env python
"""DEV ONLY — fake a handful of finished matches so the gallery can be clicked.

    python scripts/seed_dev_matches.py

The real corpus is 5,239 AFHQ photos (~700MB) plus a PyTorch install to export
the CLIP encoder, and the whole pipeline is documented in DATA_STORAGE.md §5
and §7.4. That is a long detour if what you actually want to test is accounts,
sharing and the gallery — none of which care whether the dog on the card was
chosen by a model or by ``random.choice``.

So this writes a few placeholder ``dog_assets`` rows with generated images, and
marks your existing upload jobs as finished against them.

**What this does NOT do:** any matching. The dog attached to each job is
arbitrary. Every embedding column is left NULL, so the real matcher will still
refuse to run (``NotCalibrated``) rather than quietly producing nonsense — which
is the point: a fake corpus must not be mistakable for a real one.

Refuses to run against anything but SQLite, so it cannot be pointed at the
deployed database by accident.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image, ImageDraw  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.ml import attributes  # noqa: E402
from app.models import DogAsset, UploadJob  # noqa: E402
from app.storage import layout  # noqa: E402

# The frontend names a dog by its position in this file (see src/lib/dogSrc.ts),
# so the slugs and indices have to come from it rather than be invented — an
# index that isn't in the manifest renders as the wrong dog or none at all.
MANIFEST = REPO_ROOT / "src" / "lib" / "dogImages.json"

DEFAULT_COUNT = 12


def _placeholder(slug: str, px: int) -> Image.Image:
    """A distinct, deterministic image per slug.

    Deterministic so re-running doesn't reshuffle which dog is which, and
    visibly synthetic so nobody mistakes a seeded corpus for the real one.
    """
    seed = int(hashlib.sha256(slug.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    top = (rng.randint(60, 220), rng.randint(60, 220), rng.randint(60, 220))
    bottom = tuple(max(0, c - 70) for c in top)

    image = Image.new("RGB", (px, px))
    draw = ImageDraw.Draw(image)
    for y in range(px):
        blend = y / max(1, px - 1)
        draw.line(
            [(0, y), (px, y)],
            fill=tuple(int(t + (b - t) * blend) for t, b in zip(top, bottom)),
        )
    # A paw print, so a seeded card is obviously not a photograph.
    r = px // 9
    draw.ellipse([px // 2 - r, px // 2, px // 2 + r, px // 2 + r * 2], fill=(255, 255, 255))
    for i, x in enumerate((-2.2, -0.8, 0.8, 2.2)):
        cx = px // 2 + int(x * r * 0.7)
        cy = px // 2 - r + (r // 3 if i in (0, 3) else 0)
        draw.ellipse([cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3], fill=(255, 255, 255))
    return image


def write_dog_images(slug: str) -> int:
    """Write the three derivatives the app expects. Returns the 512px size."""
    layout.ensure_dog_dirs()
    byte_size = 0
    for size, (px, _ext) in layout.DOG_SIZES.items():
        path = layout.dog_path(slug, size)
        image = _placeholder(slug, px)
        if path.suffix == ".jpg":
            image.save(path, "JPEG", quality=90)
        else:
            image.save(path, "WEBP", quality=82)
        if size == "512":
            byte_size = path.stat().st_size
    return byte_size


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT, help="how many placeholder dogs"
    )
    parser.add_argument(
        "--no-jobs",
        action="store_true",
        help="only seed dogs; leave existing upload jobs alone",
    )
    args = parser.parse_args()

    if not settings.DATABASE_URL.startswith("sqlite"):
        print(
            f"Refusing to run: DATABASE_URL is {settings.DATABASE_URL!r}.\n"
            "This writes fake data and is for a local SQLite database only.",
            file=sys.stderr,
        )
        return 2

    slugs = json.loads(MANIFEST.read_text(encoding="utf-8"))[: args.count]

    with SessionLocal() as db:
        made = 0
        for index, slug in enumerate(slugs):
            if db.query(DogAsset).filter_by(slug=slug).first():
                continue
            byte_size = write_dog_images(slug)
            db.add(
                DogAsset(
                    slug=slug,
                    checksum=hashlib.sha256(slug.encode()).hexdigest(),
                    source_split="dev",
                    width=layout.DOG_SIZES["512"][0],
                    height=layout.DOG_SIZES["512"][0],
                    byte_size=byte_size,
                    manifest_index=index,
                    # Embeddings stay NULL on purpose — see the module docstring.
                )
            )
            made += 1
        db.commit()
        print(f"seeded {made} placeholder dog(s); corpus now {db.query(DogAsset).count()}")

        if args.no_jobs:
            return 0

        dogs = db.query(DogAsset).all()
        labels = [a.label for a in attributes.ATTRIBUTES]
        pending = (
            db.query(UploadJob).filter(UploadJob.status.in_(("queued", "error"))).all()
        )
        rng = random.Random(0)
        for job in pending:
            dog = dogs[job.id % len(dogs)]
            job.status = "done"
            job.dog_asset_id = dog.id
            job.score = round(rng.uniform(0.62, 0.93), 3)
            job.shared_traits = [
                {"label": label, "strength": round(rng.uniform(0.55, 0.95), 2)}
                for label in rng.sample(labels, 3)
            ]
            job.error = None
        db.commit()
        print(f"marked {len(pending)} upload job(s) as done")

    print(
        "\nDone. Two things to know:\n"
        "  1. Restart the backend. It only mounts /dogs at startup if the corpus\n"
        "     directory already exists, so a first run needs a restart before the\n"
        "     images will load.\n"
        "  2. These dogs are arbitrary. Real matching still needs the ingest and\n"
        "     embedding passes in DATA_STORAGE.md 5 and 7.4."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
