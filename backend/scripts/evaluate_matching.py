#!/usr/bin/env python
"""Measure whether the matcher is doing anything real. Run after embed+calibrate.

    python scripts/evaluate_matching.py --faces ./lfw --sample 200

There is no ground truth here — nobody has labelled which dog a given person
"should" get, and the whole project exists because that data doesn't exist. So
this doesn't score accuracy. It checks the properties that must hold if the
model is working at all, and that visibly fail when it isn't:

1. **Diversity** — distinct people must reach distinct dogs. The characteristic
   failure of naive CLIP matching is collapse: the species gap dominates and one
   dog wins for everybody. A near-1.0 ratio means the model is discriminating.
2. **Stability** — the same photo must always give the same dog, or the demo
   contradicts itself on a refresh.
3. **Attribute grounding** — the centred attribute scores must agree with an
   independent CLIP text query. If "fluffy" in our space doesn't correlate with
   CLIP's own opinion of fluffiness, the attribute bridge is noise and the
   shared traits shown to users are decoration.
4. **Separation** — the winning dog must stand out from the corpus median by
   more than a trivial margin, otherwise the "match" is a coin flip.

Prints a table and exits non-zero if a check fails, so it can gate a release.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.ml import attributes as attrs  # noqa: E402
from app.ml.faces import NoFaceFound  # noqa: E402
from app.ml.matcher import DogMatcher  # noqa: E402
from app.ml.vectors import l2_normalize  # noqa: E402

# Thresholds are deliberately loose: they are here to catch collapse and
# scrambling, not to assert a particular quality level nobody can define.
MIN_DIVERSITY = 0.30
MIN_ATTRIBUTE_CORRELATION = 0.30
MIN_SEPARATION_SIGMA = 1.0


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation, without pulling in scipy for one function."""
    rank_a = np.argsort(np.argsort(a)).astype(np.float64)
    rank_b = np.argsort(np.argsort(b)).astype(np.float64)
    rank_a -= rank_a.mean()
    rank_b -= rank_b.mean()
    return float(rank_a @ rank_b / (np.linalg.norm(rank_a) * np.linalg.norm(rank_b)))


def evaluate(faces_dir: Path, sample: int) -> dict:
    db = SessionLocal()
    try:
        matcher = DogMatcher.build(db)
    finally:
        db.close()

    paths = sorted(p for p in faces_dir.rglob("*.jpg"))
    if not paths:
        raise SystemExit(f"no .jpg faces under {faces_dir}")
    # Evenly spaced: LFW is grouped by person, so the first N would be a
    # handful of individuals rather than a cross-section.
    if len(paths) > sample:
        step = len(paths) / sample
        paths = [paths[int(i * step)] for i in range(sample)]

    matched: list[tuple[Path, str]] = []
    separations: list[float] = []
    trait_counts: dict[str, int] = {}
    skipped = 0

    for path in paths:
        try:
            with Image.open(path) as handle:
                image = handle.convert("RGB")
            face = matcher._cropper.crop(image)
        except (NoFaceFound, OSError):
            skipped += 1
            continue

        embedding = matcher._encoder.encode(face)
        result = matcher.match_embedding(embedding)
        matched.append((path, result.slug))
        for trait in result.shared_traits:
            trait_counts[trait["label"]] = trait_counts.get(trait["label"], 0) + 1

        # How many standard deviations the winner sits above the corpus mean.
        centred = l2_normalize(embedding - matcher._human_embedding_mean)
        scores = matcher._centred_dogs @ centred
        separations.append((scores.max() - scores.mean()) / (scores.std() + 1e-9))

    if not matched:
        raise SystemExit("no usable faces — is --faces really a folder of face photos?")

    # Stability: re-run a few of the ones that worked and confirm the same
    # answer. Paired with its own path, so a skipped file can't shift the
    # comparison onto the wrong photo.
    stable = True
    for path, expected in matched[:5]:
        with Image.open(path) as handle:
            face = matcher._cropper.crop(handle.convert("RGB"))
        stable &= matcher.match_embedding(matcher._encoder.encode(face)).slug == expected

    winners = [slug for _, slug in matched]
    return {
        "matched": len(winners),
        "skipped": skipped,
        "distinct_dogs": len(set(winners)),
        "diversity": len(set(winners)) / len(winners),
        "most_common_share": max(winners.count(w) for w in set(winners)) / len(winners),
        "separation_sigma": float(np.mean(separations)),
        "stable": stable,
        "traits": sorted(trait_counts.items(), key=lambda kv: -kv[1]),
        "matcher": matcher,
    }


def attribute_grounding(matcher: DogMatcher) -> list[tuple[str, float]]:
    """Do our attribute axes measure the trait, or just themselves?

    For each attribute we have the corpus's z-scored values along the axis
    matching actually uses. The outside opinion is how each dog ranks against a
    **held-out prompt** — a different wording of the same trait that was never
    part of the ensemble those axes were built from (`Attribute.holdout`).

    Using the attribute's *own* prompt vector here, as an earlier version of
    this script did, is worthless: `dog_attribute_z[:, k]` and
    `centred_dogs @ text[k]` are the same quantity up to a per-row scale, so the
    correlation comes out at +0.997 no matter what and proves only that a number
    equals itself. A held-out wording can genuinely disagree, which is what
    makes agreement meaningful.
    """
    probes = np.load(
        Path(__file__).resolve().parents[1]
        / "app" / "ml" / "assets" / f"attribute_holdout_{attrs.ATTRIBUTE_SET}.npy"
    ).astype(np.float32)

    # The probes are mean-centred exactly as the real attribute vectors are.
    # Not doing so compares a centred axis against an uncentred reference and
    # understates agreement across the board — measured here, the mean fell
    # from +0.71 to +0.52 and "sleek" from +0.63 to +0.08, which reads as a
    # broken attribute when it is really a broken yardstick. Independence comes
    # from the wording being held out, not from the geometry being different.
    probes = l2_normalize(probes - probes.mean(axis=0))

    out = []
    for k, label in enumerate(attrs.LABELS):
        independent = matcher._centred_dogs @ l2_normalize(probes[k])
        out.append((label, _spearman(matcher._dog_attribute_z[:, k], independent)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--faces", required=True, type=Path, help="a directory of human face photos")
    parser.add_argument("--sample", type=int, default=200)
    args = parser.parse_args()

    report = evaluate(args.faces, args.sample)
    matcher = report.pop("matcher")

    print(f"\nmatched {report['matched']} faces · {report['skipped']} skipped (no face found)")
    print("\n--- does it discriminate? ---")
    print(f"  distinct dogs        {report['distinct_dogs']} / {report['matched']}")
    print(f"  diversity            {report['diversity']:.2f}   (>{MIN_DIVERSITY} required; 1.0 = never repeats)")
    print(f"  most common dog      {report['most_common_share']:.1%} of all faces   (collapse would be near 100%)")
    print(f"  separation           {report['separation_sigma']:.2f} sigma above the corpus mean   (>{MIN_SEPARATION_SIGMA} required)")
    print(f"  stable on re-run     {report['stable']}")

    grounding = attribute_grounding(matcher)
    mean_rho = float(np.mean([rho for _, rho in grounding]))
    print("\n--- are the attributes measuring anything? (rank correlation vs CLIP asked directly) ---")
    for label, rho in sorted(grounding, key=lambda kv: -kv[1]):
        print(f"  {label:<20} {rho:+.3f}")
    print(f"  mean                 {mean_rho:+.3f}   (>{MIN_ATTRIBUTE_CORRELATION} required)")

    print("\n--- which traits get reported ---")
    for label, count in report["traits"][:8]:
        print(f"  {label:<20} {count}")

    failures = []
    if report["diversity"] < MIN_DIVERSITY:
        failures.append(f"diversity {report['diversity']:.2f} — matches are collapsing onto a few dogs")
    if mean_rho < MIN_ATTRIBUTE_CORRELATION:
        failures.append(f"attribute correlation {mean_rho:.2f} — the attribute space is noise")
    if report["separation_sigma"] < MIN_SEPARATION_SIGMA:
        failures.append(f"separation {report['separation_sigma']:.2f}σ — the winner barely beats the median")
    if not report["stable"]:
        failures.append("matching is not stable across runs")

    print()
    for line in failures:
        print(f"  FAIL: {line}")
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
