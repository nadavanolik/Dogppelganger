"""CLIP's image preprocessing, in pure PIL + numpy.

**Why this is its own module.** The dog corpus is embedded offline with
PyTorch and uploaded photos are embedded at request time with onnxruntime. If
those two paths preprocessed differently — a different resize filter, a
different crop rule — the dog vectors and the human vectors would come out of
subtly different pipelines and every comparison between them would be measuring
that difference as well as the resemblance. So both call *this* function, and
neither is allowed its own.

It reimplements torchvision's `Resize(224, BICUBIC) + CenterCrop(224) +
ToTensor + Normalize` rather than importing it, because torchvision is a
PyTorch dependency and the container deliberately has no PyTorch.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

SIDE = 224

# OpenAI CLIP's channel statistics. These are part of the trained model, not a
# tunable — the weights expect inputs normalised exactly this way.
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


def preprocess(image: Image.Image) -> np.ndarray:
    """One PIL image -> a (1, 3, 224, 224) float32 batch ready for the encoder."""
    image = image.convert("RGB")

    # Shortest side to 224, aspect preserved — then take the middle square.
    width, height = image.size
    scale = SIDE / min(width, height)
    resized = image.resize(
        (max(SIDE, round(width * scale)), max(SIDE, round(height * scale))),
        Image.BICUBIC,
    )

    new_width, new_height = resized.size
    left = (new_width - SIDE) // 2
    top = (new_height - SIDE) // 2
    cropped = resized.crop((left, top, left + SIDE, top + SIDE))

    array = np.asarray(cropped, dtype=np.float32) / 255.0
    array = (array - CLIP_MEAN) / CLIP_STD
    return array.transpose(2, 0, 1)[None].astype(np.float32)
