"""The dog-matching 'model'.

Right now this is a deterministic placeholder so the whole stack works
end-to-end. Swap `predict_breed` for the real ML inference later — the API
in views.py won't need to change.
"""
import hashlib

BREEDS = [
    {"name": "Golden Retriever", "trait": "sunny optimist"},
    {"name": "Corgi", "trait": "short kingdom, big attitude"},
    {"name": "Shiba Inu", "trait": "polite chaos"},
    {"name": "French Bulldog", "trait": "professional loafer"},
    {"name": "Border Collie", "trait": "over-caffeinated genius"},
    {"name": "Dachshund", "trait": "long. very long."},
    {"name": "Husky", "trait": "screams for no reason"},
    {"name": "Pug", "trait": "snores heroically"},
]


def predict_breed(image: str | None = None) -> dict:
    """Return a breed match for the given image payload.

    Deterministic (same input -> same breed) so results are stable in demos.
    """
    seed = image or "anonymous"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(BREEDS)
    breed = BREEDS[index]
    # Fake-but-stable confidence in the 0.70–0.99 range.
    confidence = 0.70 + (int(digest[:4], 16) % 30) / 100
    return {
        "breedName": breed["name"],
        "trait": breed["trait"],
        "confidence": round(confidence, 2),
    }
