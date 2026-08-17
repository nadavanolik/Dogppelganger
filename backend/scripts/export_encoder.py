#!/usr/bin/env python
"""Export CLIP's image tower to ONNX, and bake the attribute prompts to disk.

    pip install -r requirements-ml.txt
    python scripts/export_encoder.py

Produces two files in ``app/ml/assets``:

* ``clip_image_encoder.onnx`` — the vision tower plus its projection, ~350MB.
  Not committed; the Docker build regenerates it in a stage that is thrown
  away, so the runtime image gets the graph without ever containing PyTorch.
* ``attribute_text_v1.npy`` — one unit vector per attribute in
  ``app/ml/attributes.py``, 32KB. Committed, because it is deterministic and
  having it on disk lets the matcher and its tests run with no export step.

**Only the image tower is exported.** The text tower's entire job is these
sixteen fixed prompts, so it runs once here and never again — nothing at
request time needs to encode text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from transformers import CLIPModel, CLIPTokenizer  # noqa: E402

from app.ml import attributes  # noqa: E402
from app.ml.encoder import EMBEDDING_DIM, MODEL_NAME  # noqa: E402
from app.ml.preprocess import SIDE  # noqa: E402
from app.ml.vectors import l2_normalize  # noqa: E402

ASSETS = BACKEND_DIR / "app" / "ml" / "assets"
CHECKPOINT = f"openai/{MODEL_NAME}"


class ImageTower(torch.nn.Module):
    """CLIP's vision path alone: patches -> pooled -> projected into the shared space.

    ``CLIPModel.forward`` insists on text inputs too and returns logits we have
    no use for, so the two modules we actually want are lifted out and wired
    together directly. This is exactly what ``get_image_features`` does.
    """

    def __init__(self, clip: CLIPModel) -> None:
        super().__init__()
        self.vision_model = clip.vision_model
        self.visual_projection = clip.visual_projection

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        pooled = self.vision_model(pixel_values=pixel_values)[1]
        return self.visual_projection(pooled)


def export_image_tower(clip: CLIPModel, out_path: Path) -> None:
    tower = ImageTower(clip).eval()
    dummy = torch.randn(1, 3, SIDE, SIDE)

    torch.onnx.export(
        tower,
        (dummy,),
        str(out_path),
        input_names=["pixel_values"],
        output_names=["image_embeds"],
        # Batching matters: embedding 5,239 dogs one at a time is far slower
        # than in batches, and the same graph serves single uploads at runtime.
        dynamic_axes={"pixel_values": {0: "batch"}, "image_embeds": {0: "batch"}},
        opset_version=17,
        do_constant_folding=True,
    )


def embed_attribute_prompts(clip: CLIPModel, tokenizer: CLIPTokenizer) -> np.ndarray:
    """One unit vector per attribute, averaged over its prompts.

    Averaging several wordings ("prompt ensembling") is standard CLIP practice
    and is noticeably steadier than trusting any single phrasing. Each prompt is
    normalised *before* averaging so a longer sentence with a bigger norm can't
    dominate the attribute it shares.

    **The vectors are then mean-centred, and that is not cosmetic.** CLIP's text
    embeddings all sit in a narrow cone: as exported, every pair of attributes
    here scored ~0.85 cosine against every other, so "fluffy" and "sleek" —
    opposites — came out at +0.862, essentially indistinguishable, and each
    attribute score was mostly measuring the cone rather than the trait.
    Subtracting the mean attribute removes that shared direction. Measured on
    this vocabulary it takes fluffy/sleek from +0.862 to -0.145, fluffy/shaggy
    stays positive at +0.384, golden/dark lands at +0.005, and the mean pairwise
    similarity drops from +0.851 to -0.065 — a near-orthogonal vocabulary
    instead of sixteen near-copies.

    Both species are scored with the same centred matrix, so the correction
    cancels out of nothing and biases neither side.
    """
    vectors = []
    for prompts in attributes.prompts():
        tokens = tokenizer(prompts, padding=True, return_tensors="pt")
        with torch.no_grad():
            features = clip.get_text_features(**tokens).cpu().numpy()
        averaged = l2_normalize(np.asarray(features, dtype=np.float32)).mean(axis=0)
        vectors.append(averaged)

    stacked = l2_normalize(np.stack(vectors))
    return l2_normalize(stacked - stacked.mean(axis=0)).astype(np.float32)


def verify(onnx_path: Path, clip: CLIPModel) -> float:
    """Check the exported graph agrees with PyTorch before we trust it.

    A silently wrong export would poison every embedding in the corpus, and the
    symptom — matches that feel arbitrary — is indistinguishable from the model
    simply not working well. Cheap to check, so check.
    """
    from app.ml.encoder import ClipImageEncoder

    rng = np.random.default_rng(0)
    batch = rng.standard_normal((2, 3, SIDE, SIDE), dtype=np.float32)

    onnx_out = ClipImageEncoder(onnx_path).encode_array(batch)
    with torch.no_grad():
        torch_out = ImageTower(clip).eval()(torch.from_numpy(batch)).numpy()
    torch_out = l2_normalize(torch_out)

    return float(np.abs(onnx_out - torch_out).max())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ASSETS)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"loading {CHECKPOINT} …")
    clip = CLIPModel.from_pretrained(CHECKPOINT).eval()
    tokenizer = CLIPTokenizer.from_pretrained(CHECKPOINT)

    onnx_path = args.out / "clip_image_encoder.onnx"
    print(f"exporting the image tower -> {onnx_path}")
    export_image_tower(clip, onnx_path)
    print(f"  {onnx_path.stat().st_size / 1e6:.0f}MB")

    text_path = args.out / f"attribute_text_{attributes.ATTRIBUTE_SET}.npy"
    print(f"embedding {attributes.DIM} attribute prompts -> {text_path}")
    text_vectors = embed_attribute_prompts(clip, tokenizer)
    assert text_vectors.shape == (attributes.DIM, EMBEDDING_DIM), text_vectors.shape
    np.save(text_path, text_vectors)

    if not args.skip_verify:
        drift = verify(onnx_path, clip)
        print(f"onnx vs torch, max abs difference: {drift:.2e}")
        if drift > 1e-3:
            raise SystemExit(
                f"the exported graph disagrees with PyTorch by {drift:.2e} — refusing to "
                "ship it, because every embedding in the corpus would inherit the error"
            )

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
