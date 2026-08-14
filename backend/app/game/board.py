"""Mix & Match boards: four humans, four dogs, one right answer each.

The round engine ProjectPlan 2.8 describes — "a round shows a set of people and a
set of dogs; the player links each person to a dog". Both game modes use it: solo
plays a board at a time with no clock, and a multiplayer room puts one board in
front of everybody at once (see ``rooms.py``).

Deliberately inert: no clock, no sockets, no scoring. Building a board and marking
one is all that happens here, which is why it can be tested without an event loop.

Every dog on the board belongs to one of the four humans — there are no decoys. So
a board always has a perfect answer, and a player who identifies three pairs has
identified the fourth for free. Scoring lives with the callers and accounts for
that.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import content
from .content import PoolItem

HUMANS_PER_BOARD = 4
DOGS_PER_BOARD = 4


@dataclass
class Board:
    """One dealt board. ``answer`` never leaves the server before the reveal."""

    humans: list[PoolItem]  # in display order
    dogs: list[int]  # dog indices, shuffled independently of `humans`
    answer: dict[int, int]  # human slot -> the dog slot that belongs to them

    def payload(self) -> dict:
        """The client-safe shape: who is on the board, not who goes with whom.

        Slots are array positions on both sides, so a claim is two small integers
        and the client never has to send an id back.
        """
        return {
            "humans": [
                {"slot": slot, **item.human_payload()} for slot, item in enumerate(self.humans)
            ],
            "dogs": [{"slot": slot, "dogIndex": index} for slot, index in enumerate(self.dogs)],
        }

    def answer_payload(self) -> dict[str, int]:
        """The answer key, for the reveal only. JSON object keys must be strings."""
        return {str(human): dog for human, dog in self.answer.items()}


def build_board(rng: random.Random) -> Board | None:
    """Deal a board, or None if the content pool couldn't supply one."""
    humans = content.pick_items(HUMANS_PER_BOARD, rng)
    if len(humans) < HUMANS_PER_BOARD:
        return None

    # The dogs on the board are exactly these humans' dogs, shuffled — so the two
    # columns give nothing away by their order alone.
    dogs = [item.dog_index for item in humans]
    rng.shuffle(dogs)

    return Board(
        humans=humans,
        dogs=dogs,
        answer={slot: dogs.index(item.dog_index) for slot, item in enumerate(humans)},
    )


def grade(board: Board, pairs: dict[int, int]) -> dict[int, bool]:
    """Mark a set of pairings. Humans left unpaired simply don't appear."""
    return {human: board.answer.get(human) == dog for human, dog in pairs.items()}


def correct_count(board: Board, pairs: dict[int, int]) -> int:
    return sum(1 for right in grade(board, pairs).values() if right)


def is_perfect(board: Board, pairs: dict[int, int]) -> bool:
    """True only for a full board with every pairing right."""
    return len(pairs) == len(board.humans) and correct_count(board, pairs) == len(board.humans)
