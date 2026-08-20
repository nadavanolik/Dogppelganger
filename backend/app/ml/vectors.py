"""Turning float32 vectors into database bytes and back.

Vectors are stored as raw ``float32`` in ``LargeBinary`` columns rather than in
pgvector or a Postgres array: it is portable across SQLite and Postgres, it is
compact (a 512-d vector is 2KB), and at 5,239 dogs the whole corpus is 10.7MB —
small enough to hold in RAM and scan linearly, which beats an index lookup at
this size. See DATA_STORAGE.md §4.2.
"""
from __future__ import annotations

import numpy as np

DTYPE = np.float32


def pack(vector: np.ndarray) -> bytes:
    """Vector -> bytes for a LargeBinary column."""
    return np.ascontiguousarray(vector, dtype=DTYPE).tobytes()


def unpack(blob: bytes, dim: int | None = None) -> np.ndarray:
    """Bytes -> vector. Pass `dim` to assert the stored width is what you expect.

    Worth asserting: a row embedded by a different model silently unpacks to a
    different length, and numpy would happily compare the two by broadcasting
    or fail somewhere much further from the cause.
    """
    vector = np.frombuffer(blob, dtype=DTYPE)
    if dim is not None and vector.shape[0] != dim:
        raise ValueError(f"expected a {dim}-d vector, got {vector.shape[0]}-d")
    return vector


def l2_normalize(array: np.ndarray, axis: int = -1) -> np.ndarray:
    """Scale to unit length so a dot product *is* the cosine similarity.

    Zero-length rows are left alone rather than producing NaN — they can only
    come from a degenerate image, and one bad dog shouldn't poison the whole
    matrix.
    """
    norm = np.linalg.norm(array, axis=axis, keepdims=True)
    return array / np.where(norm == 0, 1.0, norm)
