#!/usr/bin/env python
"""Load the AFHQ dog corpus into storage — see DATA_STORAGE.md §5.

Reads a directory of dog photos, writes three sanitised derivatives of each
onto the `dogdata` volume, and records a row per dog in ``dog_assets``.

    # local, against a checkout of the Kaggle dataset
    python scripts/ingest_dogs.py --source ~/afhq/dog

    # on the VM, once
    docker compose run --rm -v ~/afhq-dog:/seed:ro model \\
        python scripts/ingest_dogs.py --source /seed

Idempotent: a dog already in the database with its files intact is skipped, so
an interrupted run is resumed simply by running it again.

The dataset is deliberately NOT in git — 226MB of binaries would slow every CI
checkout. The tests generate synthetic images instead.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import DogAsset  # noqa: E402
from app.storage import layout  # noqa: E402
from app.storage.imaging import ImageRejected, write_derivatives  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# AFHQ ships three classes side by side (afhq/train/{cat,dog,wild}), so
# pointing --source at the extracted archive would otherwise ingest 16,130
# animals instead of 5,239 dogs. Skipped by directory name; a folder that
# holds only dogs has none of these and is taken whole.
NON_DOG_DIRS = {"cat", "cats", "wild"}

# Where the frontend's copy of the corpus ordering lives. Only reachable when
# running from a full checkout — the backend image doesn't ship the frontend.
MANIFEST_PATH = BACKEND_DIR.parent / "src" / "lib" / "dogImages.json"


# --------------------------------------------------------------- discovery


def discover(source: Path) -> list[tuple[Path, str, str]]:
    """Find every image under `source` as (path, slug, split).

    Handles both AFHQ's own ``train/dog`` + ``val/dog`` layout and a flat
    directory, because which one you get depends on how the Kaggle archive was
    unpacked and it is not worth making the operator care. Cats and wild
    animals are skipped, so ``--source`` can point at the whole archive.
    """
    if not source.is_dir():
        raise SystemExit(f"--source {source} is not a directory")

    found: list[tuple[Path, str, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        # "train" / "val" if either appears in the path, else "unknown".
        parts = {p.lower() for p in path.relative_to(source).parts}
        if parts & NON_DOG_DIRS:
            continue
        split = "train" if "train" in parts else "val" if "val" in parts else "unknown"
        found.append((path, path.stem, split))

    slugs: dict[str, Path] = {}
    for path, slug, _ in found:
        if slug in slugs:
            raise SystemExit(
                f"two source files share the name {slug!r} ({slugs[slug]} and {path}).\n"
                "Slugs must be unique — they name the files nginx serves."
            )
        slugs[slug] = path
    return found


# ------------------------------------------------------------- the CPU work


def _process_one(job: tuple[str, str, str]) -> dict:
    """Decode one source image and write its derivatives. Runs in a subprocess.

    Module-level and taking only picklable arguments because that is what
    ProcessPoolExecutor requires. The child inherits DOG_DATA_DIR from the
    environment, so `layout` resolves to the same volume as the parent.
    """
    path_str, slug, split = job
    path = Path(path_str)
    try:
        data = path.read_bytes()
        targets = {
            layout.dog_path(slug, size): spec for size, spec in layout.DOG_SIZES.items()
        }
        stored = write_derivatives(data, targets)
    except ImageRejected as exc:
        return {"slug": slug, "error": str(exc)}
    except OSError as exc:
        return {"slug": slug, "error": f"could not read {path.name}: {exc}"}

    return {
        "slug": slug,
        "split": split,
        "checksum": stored.checksum,
        "width": stored.width,
        "height": stored.height,
        "byte_size": stored.byte_size,
    }


def _already_complete(slug: str) -> bool:
    """True when every derivative for this slug is on disk."""
    return all(layout.dog_path(slug, size).exists() for size in layout.DOG_SIZES)


# ----------------------------------------------------------------- manifest


def report_duplicates(db) -> list[tuple[str, int]]:
    """Groups of dogs whose pixels are byte-identical.

    Not an error — AFHQ genuinely ships the same photo under more than one
    filename — but worth printing, because a duplicated dog is proportionally
    more likely to be retrieved than a unique one, which quietly biases the
    matching. Dropping them is a decision for the embedding phase.
    """
    rows = (
        db.query(DogAsset.checksum, func.count(DogAsset.id))
        .group_by(DogAsset.checksum)
        .having(func.count(DogAsset.id) > 1)
        .all()
    )
    return [(checksum, count) for checksum, count in rows]


def _manifest_from_db(db) -> list[str]:
    """The corpus ordering the frontend must agree with: slugs, sorted."""
    return [slug for (slug,) in db.query(DogAsset.slug).order_by(DogAsset.slug).all()]


def assign_manifest_indices(db) -> list[str]:
    """Deal out `manifest_index` in slug order and return that ordering.

    Done in one pass at the end rather than per-insert so the numbering depends
    only on which dogs exist, never on the order they happened to be ingested.
    """
    slugs = _manifest_from_db(db)
    by_slug = {d.slug: d for d in db.query(DogAsset).all()}
    # Clear first: indices are unique, so shifting them in place would collide
    # with a row that hasn't been renumbered yet.
    for dog in by_slug.values():
        dog.manifest_index = None
    db.flush()
    for index, slug in enumerate(slugs):
        by_slug[slug].manifest_index = index
    db.commit()
    return slugs


def check_manifest(slugs: list[str], manifest_path: Path, write: bool) -> None:
    """Keep the database and src/lib/dogImages.json in lockstep.

    The backend names a dog to the frontend by its index into that file, but
    the file is baked into the site image at build time while this script runs
    on the VM at runtime — so they can drift. We fail loudly instead of serving
    5,239 subtly wrong dogs. See DATA_STORAGE.md §5.3.
    """
    if write:
        if not manifest_path.parent.is_dir():
            raise SystemExit(
                f"--write-manifest needs a full checkout; {manifest_path.parent} does not exist.\n"
                "Run it on your machine, not inside the backend container."
            )
        manifest_path.write_text(json.dumps(slugs, indent=4) + "\n")
        print(f"manifest written: {manifest_path} ({len(slugs)} dogs)")
        return

    if not manifest_path.exists():
        print(f"note: no manifest at {manifest_path} to verify (fine inside the container)")
        return

    committed = json.loads(manifest_path.read_text())
    if committed == slugs:
        print(f"manifest verified: {len(slugs)} dogs, order matches")
        return

    extra = len(slugs) - len(committed)
    raise SystemExit(
        f"MANIFEST MISMATCH — the database has {len(slugs)} dogs, "
        f"src/lib/dogImages.json has {len(committed)} ({extra:+d}).\n"
        "The frontend resolves dog indices through that file, so leaving this "
        "would show the wrong dog for every match.\n"
        "Re-run with --write-manifest on a full checkout, then commit the result."
    )


# --------------------------------------------------------------------- main


def ingest(source: Path, limit: int | None, workers: int) -> tuple[int, int, list[str]]:
    """Returns (ingested, skipped, errors)."""
    Base.metadata.create_all(bind=engine)
    layout.ensure_dog_dirs()

    found = discover(source)
    if limit:
        found = found[:limit]
    if not found:
        raise SystemExit(f"no images found under {source}")

    db = SessionLocal()
    try:
        known = {slug for (slug,) in db.query(DogAsset.slug).all()}
        # Skip only when the row AND its files are present: a row whose
        # derivatives were lost with a volume must be redone.
        pending = [
            (str(path), slug, split)
            for path, slug, split in found
            if slug not in known or not _already_complete(slug)
        ]
        skipped = len(found) - len(pending)
        print(f"{len(found)} images found · {skipped} already ingested · {len(pending)} to do")

        errors: list[str] = []
        ingested = 0
        if pending:
            # Decode + resize is CPU-bound C code outside the GIL, so processes
            # beat threads here: ~7 minutes down to ~90 seconds on four cores.
            with ProcessPoolExecutor(max_workers=workers) as pool:
                for done, result in enumerate(pool.map(_process_one, pending, chunksize=16), 1):
                    if result.get("error"):
                        errors.append(f"{result['slug']}: {result['error']}")
                        continue

                    dog = db.query(DogAsset).filter_by(slug=result["slug"]).one_or_none()
                    if dog is None:
                        dog = DogAsset(slug=result["slug"])
                        db.add(dog)
                    dog.checksum = result["checksum"]
                    dog.source_split = result["split"]
                    dog.width = result["width"]
                    dog.height = result["height"]
                    dog.byte_size = result["byte_size"]
                    ingested += 1

                    if done % 250 == 0:
                        db.commit()
                        print(f"  … {done}/{len(pending)}")
            db.commit()

        return ingested, skipped, errors
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="directory of dog photos")
    parser.add_argument("--limit", type=int, help="only ingest the first N (for a smoke test)")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, (os.cpu_count() or 2)),
        help="decode/resize processes (default: CPU count, capped at 8)",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="regenerate src/lib/dogImages.json instead of verifying it",
    )
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()

    ingested, skipped, errors = ingest(args.source, args.limit, args.workers)

    db = SessionLocal()
    try:
        slugs = assign_manifest_indices(db)
        duplicates = report_duplicates(db)
    finally:
        db.close()

    print(f"\ningested {ingested} · skipped {skipped} · rejected {len(errors)}")
    for line in errors[:20]:
        print(f"  ! {line}")
    if len(errors) > 20:
        print(f"  … and {len(errors) - 20} more")
    if duplicates:
        repeats = sum(count - 1 for _, count in duplicates)
        print(
            f"note: {len(duplicates)} photo(s) appear more than once "
            f"({repeats} redundant copies). Kept — see DATA_STORAGE.md §5.2."
        )

    check_manifest(slugs, args.manifest_path, args.write_manifest)
    print(f"corpus now holds {len(slugs)} dogs at {layout.dog_root()}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
