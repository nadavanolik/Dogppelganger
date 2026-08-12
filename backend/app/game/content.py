"""Where game content comes from — THE DATA SEAM.

A game round needs human↔dog pairs. Eventually those are real shared matches out
of the gallery. Until that exists, this module invents them deterministically so
the games are fully playable with no database, no image storage and no assets
beyond the dog photos already committed to ``public/dogs``.

**How images travel.** The backend never handles image bytes:

* A dog is identified by its *index* into ``src/lib/dogImages.json`` (5,239
  photos, already served by nginx). The frontend maps index -> filename, so the
  backend needs one integer, not a copy of the list.
* A human is identified by a *seed string*. The frontend draws a deterministic
  cartoon face from it. When real photos exist, ``human_url`` is filled in
  instead and the frontend prefers it — no protocol change.

**Replacing this module.** Rewrite ``pick_items`` and ``pick_decoy_dogs`` to read
real shared matches (Postgres, Mongo, anything) and return ``PoolItem``s. Every
other file in the package keeps working untouched.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from ..config import settings

# Length of src/lib/dogImages.json. The frontend takes the index modulo its own
# list length, so a mismatch degrades to "some dogs never appear" rather than a
# broken image.
DOG_POOL_SIZE = 5239


@dataclass(frozen=True)
class PoolItem:
    """One human and the dog that is *the* right answer for them."""

    id: str
    human_seed: str
    dog_index: int
    human_url: str | None = None

    def human_payload(self) -> dict:
        return {"id": self.id, "humanSeed": self.human_seed, "humanUrl": self.human_url}


def _human_seed_for(dog_index: int) -> str:
    """A stable, arbitrary-looking face seed for a given dog.

    Stable matters: the same pair always looks the same, so a player who sees a
    face twice across runs isn't told two different truths.

    Mixed with ``SECRET_KEY`` so the pairing isn't a hash a clever player could
    recompute in the browser to spot the right dog without guessing. (Changing
    the secret reshuffles which face goes with which dog — harmless for made-up
    content, and moot once real matches come from the database.)
    """
    return hashlib.sha1(f"human:{settings.SECRET_KEY}:{dog_index}".encode()).hexdigest()[:12]


def _item(dog_index: int) -> PoolItem:
    return PoolItem(
        id=f"pool_{dog_index}",
        human_seed=_human_seed_for(dog_index),
        dog_index=dog_index,
    )


def pick_items(count: int, rng: random.Random, exclude: set[str] | None = None) -> list[PoolItem]:
    """Return `count` distinct pool items, skipping any id in `exclude`."""
    exclude = exclude or set()
    picked: list[PoolItem] = []
    seen: set[int] = set()
    # Bounded so a nearly-exhausted pool can't spin forever; an endless solo run
    # would have to answer thousands of questions to get near it.
    for _ in range(count * 20):
        if len(picked) == count:
            break
        dog_index = rng.randrange(DOG_POOL_SIZE)
        item = _item(dog_index)
        if dog_index in seen or item.id in exclude:
            continue
        seen.add(dog_index)
        picked.append(item)
    return picked


def pick_decoy_dogs(count: int, rng: random.Random, exclude: set[int]) -> list[int]:
    """Return `count` distinct dog indices that aren't in `exclude`.

    Decoys are other humans' dogs, which is what makes the question fair: every
    option is a real dog from the pool, not a doctored one.
    """
    decoys: list[int] = []
    taken = set(exclude)
    for _ in range(count * 20):
        if len(decoys) == count:
            break
        dog_index = rng.randrange(DOG_POOL_SIZE)
        if dog_index in taken:
            continue
        taken.add(dog_index)
        decoys.append(dog_index)
    return decoys
