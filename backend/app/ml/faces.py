"""Find the face in an uploaded photo and crop to it.

**Why this is not optional.** AFHQ dog photos are tight, centred crops of a
head. An uploaded human photo is whatever someone had on their phone — full
body, a group at a party, a busy room. Embed that whole frame and most of the
vector describes the sofa, so matches become both worse and inexplicable.
Cropping to the face is the single biggest quality lever in the pipeline: it
makes the human input look like the corpus it is being compared against.

It also answers the guidelines' requirement that the system be robust to "a
user entering a picture that is meant to make the model not output a dog" — no
face, no match, with a clear reason rather than a confident dog for a photo of
a sandwich.

Uses YuNet (232KB, vendored in `assets/`) through OpenCV rather than a Haar
cascade: Haar ships free with OpenCV but only finds well-lit frontal faces, and
silently missing a face means falling back to the whole frame, which is the
failure this module exists to prevent.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

MODEL_PATH = Path(__file__).parent / "assets" / "yunet_face_detection_2023mar.onnx"

# Detection confidence. 0.6 is deliberately not permissive: a false positive
# crops to a patch of wallpaper and matches that, which looks far more broken
# to a user than being told no face was found.
SCORE_THRESHOLD = 0.6
NMS_THRESHOLD = 0.3
TOP_K = 50

# YuNet's cost scales with input pixels and it detects fine at this size, so a
# 12MP phone photo is downscaled before detection and the box scaled back up.
DETECT_MAX_SIDE = 1024

# How much context to keep around the detector's box. YuNet returns roughly
# eyes-to-chin; AFHQ crops include the whole head with ears and fur, so we
# widen to match. Matching the corpus's framing matters more than tightness.
DEFAULT_MARGIN = 0.45


class NoFaceFound(Exception):
    """No face in the photo, so there is nothing to match.

    The message is shown to the user, so it says what to do about it.
    """

    def __init__(self) -> None:
        super().__init__(
            "we couldn't find a face in that photo — try a clearer, "
            "front-facing picture of one person"
        )


class FaceCropper:
    """Wraps YuNet. Construct once and reuse: loading the model isn't free."""

    def __init__(self, model_path: Path | None = None, score_threshold: float = SCORE_THRESHOLD):
        path = model_path or MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"the face detector is missing at {path} — it is vendored in the repo, "
                "so this usually means an incomplete checkout"
            )
        self._detector = cv2.FaceDetectorYN.create(
            str(path), "", (320, 320), score_threshold, NMS_THRESHOLD, TOP_K
        )

    def detect(self, image: Image.Image) -> tuple[float, float, float, float] | None:
        """The most prominent face as (x, y, w, h) in original-image pixels."""
        rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]

        scale = min(1.0, DETECT_MAX_SIDE / max(height, width))
        if scale < 1.0:
            small = cv2.resize(rgb, (int(width * scale), int(height * scale)))
        else:
            small = rgb
        bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)

        self._detector.setInputSize((bgr.shape[1], bgr.shape[0]))
        _, faces = self._detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return None

        # Largest box, not highest score: in a group photo the subject is the
        # person nearest the camera, and that is the one worth matching.
        best = max(faces, key=lambda f: float(f[2]) * float(f[3]))
        x, y, w, h = (float(v) / scale for v in best[:4])
        return x, y, w, h

    def crop(self, image: Image.Image, margin: float = DEFAULT_MARGIN) -> Image.Image:
        """Crop to a square around the face. Raises `NoFaceFound` if there isn't one."""
        box = self.detect(image)
        if box is None:
            raise NoFaceFound()

        x, y, w, h = box
        width, height = image.size
        centre_x, centre_y = x + w / 2, y + h / 2

        # A square keeps the aspect ratio the encoder's centre-crop expects, so
        # widening for context doesn't also squash the face.
        side = min(max(w, h) * (1 + 2 * margin), float(width), float(height))

        # Slide the square back inside the frame rather than shrinking it — a
        # face near the edge should still get its full context on the other side.
        left = int(round(min(max(centre_x - side / 2, 0.0), width - side)))
        top = int(round(min(max(centre_y - side / 2, 0.0), height - side)))
        edge = int(round(side))
        return image.crop((left, top, left + edge, top + edge))
