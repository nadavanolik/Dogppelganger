"""Accepting an image or a video attached to a direct message.

Images go through the same pipeline as an upload: decoded (which *proves* the
bytes are an image), stripped of EXIF/GPS, and re-encoded into a display and a
thumbnail derivative. See `app/storage/imaging.py`.

**Video cannot be validated that way, and this module does not pretend
otherwise.** There is no decoder here — shipping ffmpeg to transcode or even to
probe would add 100MB+ to an image that already carries a 350MB ONNX encoder,
and minutes of CPU per clip on a 1GB VM that is also running Postgres and a
matcher. So a video is stored exactly as received, and the defences are
arranged around that fact:

* the container is identified from its own magic bytes, never from the
  `Content-Type` header or the filename the client sent;
* the extension on disk and the `Content-Type` in the response both come from
  our allowlist, so a mislabelled file cannot be served as something else;
* the response carries `X-Content-Type-Options: nosniff`;
* nginx never serves this directory — every read goes through the participant
  check in the router;
* the size cap is enforced *while streaming*, so a 4GB body is refused after
  one megabyte rather than after it has been buffered.

The consequence to be honest about: we accept that an `.mp4` might be a
well-formed file that no browser can play. It cannot be anything dangerous, but
it might disappoint.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from ..storage import layout

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024

# Read in 1MB slices. Starlette spools an UploadFile past ~1MB to a temp file,
# so the real ceiling without this is disk rather than RAM — but streaming keeps
# both bounded and turns "out of space" into a clean 413.
CHUNK = 1024 * 1024
SNIFF_BYTES = 32


class AttachmentRejected(ValueError):
    """A file we will not store, with a message safe to show the sender."""


# MP4 and HEIC and QuickTime all begin with a size field followed by `ftyp` at
# offset 4; only the *brand* at offset 8 tells them apart. A sniffer that stops
# at `ftyp` will happily store an iPhone .mov as .mp4, and then no Chrome user
# can play it.
_MP4_BRANDS = {b"isom", b"iso2", b"iso4", b"mp41", b"mp42", b"avc1", b"mp4v", b"dash"}
_REJECT_BRANDS = {
    b"qt  ": "QuickTime (.mov) can't be played by every browser — export as MP4 first.",
    b"heic": "iPhone HEIC photos aren't supported yet — send a JPEG.",
    b"heix": "iPhone HEIC photos aren't supported yet — send a JPEG.",
    b"mif1": "iPhone HEIC photos aren't supported yet — send a JPEG.",
}


def sniff(head: bytes) -> str | None:
    """The real content type of a file, from its first bytes. None if unknown."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"\x1a\x45\xdf\xa3":  # EBML — Matroska/WebM
        return "video/webm"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in _MP4_BRANDS:
            return "video/mp4"
        if brand in _REJECT_BRANDS:
            raise AttachmentRejected(_REJECT_BRANDS[brand])
        return None
    return None


def cap_for(content_type: str) -> int:
    kind, _ = layout.ATTACHMENT_TYPES[content_type]
    return MAX_VIDEO_BYTES if kind == "video" else MAX_IMAGE_BYTES


def _too_big(content_type: str) -> AttachmentRejected:
    kind, _ = layout.ATTACHMENT_TYPES[content_type]
    if kind == "video":
        # Megabytes mean nothing to someone holding a phone; seconds do.
        return AttachmentRejected(
            "That video is too big — the limit is 25MB, which is roughly 20 seconds "
            "of phone video. Try trimming it."
        )
    return AttachmentRejected("That image is too big — the limit is 10MB.")


async def read_validated(upload: UploadFile) -> tuple[str, bytes | None, Path | None]:
    """Identify an attachment and, for video, stream it to a temporary file.

    Returns ``(content_type, data, temp_path)``. Images come back as bytes,
    because they are about to be decoded and re-encoded anyway and are capped at
    10MB. Video comes back as a path — it is never held in memory whole.
    """
    head = await upload.read(SNIFF_BYTES)
    if not head:
        raise AttachmentRejected("That file is empty.")

    content_type = sniff(head)
    if content_type is None or content_type not in layout.ATTACHMENT_TYPES:
        raise AttachmentRejected(
            "That file type isn't supported. Send a JPEG, PNG or WebP image, "
            "or an MP4 or WebM video."
        )

    kind, _ = layout.ATTACHMENT_TYPES[content_type]
    cap = cap_for(content_type)

    if kind == "image":
        data = head + await upload.read(cap + 1 - len(head))
        if len(data) > cap:
            raise _too_big(content_type)
        return content_type, data, None

    # Video: straight to disk, refusing as soon as the running total passes the
    # cap, and leaving no partial file behind when it does.
    import tempfile

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".part")
    temp_path = Path(handle.name)
    total = len(head)
    try:
        handle.write(head)
        while True:
            chunk = await upload.read(CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise _too_big(content_type)
            handle.write(chunk)
    except BaseException:
        handle.close()
        temp_path.unlink(missing_ok=True)
        raise
    handle.close()
    return content_type, None, temp_path


def store_video(message_id: int, content_type: str, temp_path: Path) -> int:
    """Move a validated video into place. Returns its size in bytes."""
    layout.ensure_attachment_dirs(message_id)
    destination = layout.attachment_path(message_id, content_type)
    size = temp_path.stat().st_size
    # Replace rather than rename: the temp file may be on another filesystem.
    destination.write_bytes(temp_path.read_bytes())
    temp_path.unlink(missing_ok=True)
    return size
