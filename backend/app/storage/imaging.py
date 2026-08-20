"""Decode, sanitise and resize — the only way an image becomes a stored file.

The rule this module exists to enforce: **we never store the bytes a client
sent us.** Every image is decoded by Pillow and re-encoded from the pixel data,
which is what actually strips EXIF (including GPS), bakes in the orientation
tag so photos aren't sideways, and destroys anything smuggled into a metadata
segment. A renamed executable or a decompression bomb dies here with a reason
attached, not as a traceback in a worker.

See DATA_STORAGE.md §6.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# A 50 MP ceiling: comfortably above any phone camera, far below the pixel
# counts that make a "bomb" work. Pillow warns at this figure and refuses at
# twice it, so we also check the decoded size ourselves for a hard stop.
MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

JPEG_QUALITY = 90
WEBP_QUALITY = 82

# Metadata that Pillow will happily carry from the source into the output if we
# let it. Dropped explicitly rather than trusting each format plugin's defaults.
_METADATA_KEYS = ("exif", "icc_profile", "XML:com.adobe.xmp", "xmp", "comment", "dpi")


class ImageRejected(Exception):
    """The bytes are not an image we are willing to store.

    Carries a message safe to show a user — it is echoed straight back in the
    upload endpoint's `rejected` list.
    """


@dataclass(frozen=True)
class StoredImage:
    """What ended up on disk, for the caller to record in the database."""

    checksum: str  # SHA-256 of the *source* bytes — the ingest idempotency key
    width: int  # of the largest derivative written
    height: int
    byte_size: int  # of the largest derivative written


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes) -> Image.Image:
    """Bytes -> a sanitised RGB image, or raise `ImageRejected`.

    Two passes over the buffer on purpose: `verify()` checks structural
    integrity but leaves the image unusable afterwards, so the real decode has
    to reopen. It is cheap relative to the resize that follows.
    """
    if not data:
        raise ImageRejected("the file is empty")

    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
    except Image.DecompressionBombError:
        raise ImageRejected("that image is too large to process safely") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageRejected("that file isn't a readable image") from None

    try:
        with Image.open(BytesIO(data)) as opened:
            width, height = opened.size
            if width * height > MAX_PIXELS:
                raise ImageRejected("that image is too large to process safely")
            # Applies the EXIF orientation tag as an actual rotation, so the
            # pixels are upright once the tag itself is thrown away below.
            upright = ImageOps.exif_transpose(opened)
            # Flattens RGBA/P/LA onto white and settles on one channel layout,
            # so every stored file and every model input looks the same.
            image = upright.convert("RGB")
    except Image.DecompressionBombError:
        raise ImageRejected("that image is too large to process safely") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageRejected("that file isn't a readable image") from None

    if min(image.size) < 1:
        raise ImageRejected("that image has no pixels")

    for key in _METADATA_KEYS:
        image.info.pop(key, None)
    return image


def _encode(image: Image.Image, target_px: int, suffix: str) -> bytes:
    """One derivative, as bytes. Never upscales — a 200px photo stays 200px."""
    resized = image.copy()
    # `thumbnail` preserves the aspect ratio and is a no-op when the image is
    # already inside the box. We deliberately don't centre-crop to a square:
    # cropping a phone photo is a good way to cut someone's face in half, and
    # the frontend already uses object-cover to fill its tiles.
    resized.thumbnail((target_px, target_px), Image.LANCZOS)
    for key in _METADATA_KEYS:
        resized.info.pop(key, None)

    buffer = BytesIO()
    if suffix == ".webp":
        resized.save(buffer, "WEBP", quality=WEBP_QUALITY, method=4)
    else:
        resized.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buffer.getvalue()


def write_derivatives(
    data: bytes,
    targets: dict[Path, tuple[int, str]],
    image: Image.Image | None = None,
) -> StoredImage:
    """Decode `data` once, then write every requested derivative.

    `targets` maps an output path to `(longest_edge_px, suffix)` — the shape
    `layout.DOG_SIZES` / `layout.UPLOAD_SIZES` already describe, so callers pass
    those through rather than inventing sizes.

    Pass `image` when you have already called `decode` (the upload endpoint
    validates before it creates a job row, and there is no sense decoding the
    same phone photo twice). `data` is still required — the checksum has to be
    of the source bytes, not of what we re-encoded.

    Files are written largest-first so that the returned dimensions describe the
    archival copy, which is the one the model reads.
    """
    if image is None:
        image = decode(data)
    largest: StoredImage | None = None

    for path, (target_px, suffix) in sorted(targets.items(), key=lambda kv: -kv[1][0]):
        encoded = _encode(image, target_px, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)

        if largest is None:
            with Image.open(BytesIO(encoded)) as written:
                width, height = written.size
            largest = StoredImage(
                checksum=checksum_of(data),
                width=width,
                height=height,
                byte_size=len(encoded),
            )

    if largest is None:
        raise ValueError("write_derivatives needs at least one target")
    return largest
