"""The on-disk contract for stored images — see DATA_STORAGE.md §3.

Both volumes are configured by environment variable so that the same code runs
three ways with no branching: a temp directory under pytest, a `data/` folder
next to the backend in local dev, and a Docker named volume in production.

    DOG_DATA_DIR     dog corpus      -> `dogdata` volume, /data/dogs
    UPLOAD_DATA_DIR  user uploads    -> `appdata` volume, /app/data/uploads

Nothing outside this module should join these paths by hand: the dog corpus is
mounted read-only into the nginx container at a fixed layout, so a stray
directory name is a 404 nobody notices until the demo.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------- dog corpus

# Three derivatives per dog. 512 is the archival copy (AFHQ's native size);
# 256 is what the gallery and result pages show; 128 is a game tile. They are
# generated once at ingest rather than on request — the corpus never changes,
# so resizing on the fly would be pure waste.
DOG_ARCHIVE_PX = 512
DOG_DISPLAY_PX = 256
DOG_THUMB_PX = 128

# Directory name -> file extension. The archive stays JPEG because that is what
# the source is; the smaller two are WebP, which is ~30% smaller than JPEG at
# the same quality and is supported by every browser we care about.
DOG_SIZES: dict[str, tuple[int, str]] = {
    "512": (DOG_ARCHIVE_PX, ".jpg"),
    "256": (DOG_DISPLAY_PX, ".webp"),
    "128": (DOG_THUMB_PX, ".webp"),
}


def dog_root() -> Path:
    """Root of the dog corpus. Read at call time, not import time, so tests can
    point it somewhere else after the module is already loaded."""
    return Path(os.getenv("DOG_DATA_DIR", "data/dogs"))


def dog_path(slug: str, size: str = "512") -> Path:
    """Absolute path to one derivative of one dog.

    `slug` is the stable name without extension (``flickr_dog_000002``); it is
    also `DogAsset.slug`, which is what makes a row and its files findable from
    each other without storing three more path columns.
    """
    if size not in DOG_SIZES:
        raise ValueError(f"unknown dog image size {size!r}; expected one of {sorted(DOG_SIZES)}")
    _, ext = DOG_SIZES[size]
    return dog_root() / size / f"{slug}{ext}"


def dog_filename(slug: str, size: str = "512") -> str:
    """The basename nginx serves for a dog, e.g. ``flickr_dog_000002.jpg``."""
    return dog_path(slug, size).name


def ensure_dog_dirs() -> None:
    for size in DOG_SIZES:
        (dog_root() / size).mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------- user uploads

UPLOAD_ORIGINAL_PX = 1024
UPLOAD_DISPLAY_PX = 512
UPLOAD_THUMB_PX = 256

# "orig" is a re-encoded original, not the client's bytes — see imaging.py.
# It is the copy the matching model reads, so it keeps the most detail.
UPLOAD_SIZES: dict[str, tuple[int, str]] = {
    "orig": (UPLOAD_ORIGINAL_PX, ".jpg"),
    "display": (UPLOAD_DISPLAY_PX, ".webp"),
    "thumb": (UPLOAD_THUMB_PX, ".webp"),
}

# Files per shard directory. A single directory holding tens of thousands of
# entries degrades badly on ext4; sharding on the job id (rather than on a hash
# of the owner) keeps nothing user-identifying in the path.
SHARD_SIZE = 1000


def upload_root() -> Path:
    return Path(os.getenv("UPLOAD_DATA_DIR", "data/uploads"))


def upload_shard(job_id: int) -> Path:
    return upload_root() / f"{job_id // SHARD_SIZE:04d}"


def upload_path(job_id: int, size: str = "orig") -> Path:
    if size not in UPLOAD_SIZES:
        raise ValueError(f"unknown upload size {size!r}; expected one of {sorted(UPLOAD_SIZES)}")
    _, ext = UPLOAD_SIZES[size]
    return upload_shard(job_id) / f"{job_id}-{size}{ext}"


def ensure_upload_dirs(job_id: int) -> None:
    upload_shard(job_id).mkdir(parents=True, exist_ok=True)


def legacy_upload_path(job_id: int, content_type: str) -> Path:
    """Where uploads lived before sharding and derivatives existed.

    Kept so a volume seeded by the previous build still serves its images
    instead of 404ing after a deploy. Nothing writes here any more.
    """
    ext = {"image/png": ".png", "image/jpeg": ".jpg"}.get(content_type, "")
    return upload_root() / f"{job_id}{ext}"


def delete_upload_files(job_id: int, content_type: str | None = None) -> int:
    """Remove every derivative of one upload. Returns how many files went.

    Retention rule (DATA_STORAGE.md §6): an upload's bytes live exactly as long
    as its job row, so deleting the row must call this.
    """
    removed = 0
    paths = [upload_path(job_id, size) for size in UPLOAD_SIZES]
    if content_type:
        paths.append(legacy_upload_path(job_id, content_type))
    for path in paths:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return removed
