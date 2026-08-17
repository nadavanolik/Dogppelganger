"""The CLIP image encoder at request time, under onnxruntime.

PyTorch never enters the container. The dog corpus is embedded offline with
torch (`scripts/embed_dogs.py`), the encoder is exported once
(`scripts/export_encoder.py`), and what ships is a ~350MB ONNX graph plus
onnxruntime's ~15MB — against roughly 2GB for a torch install that CI would
push and the VM would pull on every single deploy.

Only the *image* tower is exported. The text tower's job is done offline: the
attribute prompts are fixed, so their embeddings are computed once and stored,
and nothing at request time needs to encode text.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from .preprocess import preprocess
from .vectors import l2_normalize

# Overridable so tests can point at a tiny stand-in graph instead of 350MB.
DEFAULT_MODEL_PATH = Path(
    os.getenv("CLIP_ONNX_PATH", str(Path(__file__).parent / "assets" / "clip_image_encoder.onnx"))
)

MODEL_NAME = "clip-vit-base-patch32"
EMBEDDING_DIM = 512


class EncoderMissing(RuntimeError):
    """The exported encoder isn't on disk.

    Unlike the face detector this is too big to vendor, so it is built by a
    setup step. Raised with the command that fixes it.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"the CLIP image encoder is missing at {path} — run "
            "`python scripts/export_encoder.py` (see DATA_STORAGE.md §7)"
        )


class ClipImageEncoder:
    """Construct once and reuse — building a session parses the whole graph."""

    def __init__(self, model_path: Path | None = None) -> None:
        path = model_path or DEFAULT_MODEL_PATH
        if not path.exists():
            raise EncoderMissing(path)

        options = ort.SessionOptions()
        # One thread per session. The queue already runs several workers, and
        # letting each spawn its own thread pool oversubscribes a small VM and
        # makes everything slower, not faster.
        options.intra_op_num_threads = int(os.getenv("ONNX_THREADS", "1"))
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self._session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input = self._session.get_inputs()[0].name

    def encode_array(self, batch: np.ndarray) -> np.ndarray:
        """Preprocessed (N, 3, 224, 224) batch -> (N, dim), L2-normalised.

        Normalising here means every downstream comparison is a plain dot
        product, and nothing else has to remember to do it.
        """
        raw = self._session.run(None, {self._input: batch.astype(np.float32)})[0]
        return l2_normalize(np.asarray(raw, dtype=np.float32))

    def encode(self, image: Image.Image) -> np.ndarray:
        """One PIL image -> a (dim,) unit vector."""
        return self.encode_array(preprocess(image))[0]

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        """Several images in one graph call, which is markedly faster per image."""
        if not images:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        batch = np.concatenate([preprocess(image) for image in images], axis=0)
        return self.encode_array(batch)
