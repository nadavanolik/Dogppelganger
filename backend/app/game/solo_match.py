"""Single-player Mix & Match.

Four humans, four dogs, link them all up and submit. **No timer** — think as long
as you like. Three lives; a board that isn't perfect costs one. The run ends at
zero lives and the score is how many pairs you got right in total.

*Why a life per board rather than per wrong pair:* matching four humans to four
distinct dogs, you can never be wrong on exactly one — swapping two is the
smallest possible mistake, so the wrong count is always 0, 2, 3 or 4. Charging per
wrong pair would make a single slip cost two lives and end most runs on the second
board.

Boards are served one at a time against a run token so the answer key stays on the
server. There is no clock and no shared state, so plain REST is enough — no
WebSocket needed for this mode (same reasoning as ``solo.py``).
"""
from __future__ import annotations

import random
import secrets
import time
from dataclasses import dataclass, field

from . import board as boards
from . import store
from .board import Board

STARTING_LIVES = 3

# Abandoned runs (closed tab, lost phone) are swept once they go quiet. Generous,
# because there is no timer pressuring the player to hurry.
RUN_IDLE_TIMEOUT = 60 * 60


@dataclass
class Run:
    token: str
    player_id: str
    name: str
    rng: random.Random
    lives: int = STARTING_LIVES
    correct: int = 0
    boards_played: int = 0
    perfect_streak: int = 0
    longest_streak: int = 0
    board: Board | None = None
    over: bool = False
    last_seen: float = field(default_factory=time.monotonic)


_runs: dict[str, Run] = {}


class UnknownRun(Exception):
    """Raised for a token that never existed, expired, or is already finished."""


def _sweep() -> None:
    cutoff = time.monotonic() - RUN_IDLE_TIMEOUT
    for token in [t for t, run in _runs.items() if run.last_seen < cutoff]:
        _runs.pop(token, None)


def _deal(run: Run) -> Board | None:
    run.board = boards.build_board(run.rng)
    return run.board


def _state(run: Run) -> dict:
    return {
        "runToken": run.token,
        "lives": run.lives,
        "score": run.correct,
        "boardsPlayed": run.boards_played,
        "streak": run.perfect_streak,
        "longestStreak": run.longest_streak,
        "over": run.over,
        "board": run.board.payload() if run.board and not run.over else None,
    }


def _finish(run: Run) -> None:
    run.over = True
    run.board = None
    store.record_solo_run(
        run.player_id,
        run.name,
        run.correct,
        run.longest_streak,
        board=store.BOARD_SOLO_MATCH,
    )
    _runs.pop(run.token, None)


def start_run(player_id: str, name: str) -> dict:
    """Begin a run and hand back its first board."""
    _sweep()
    run = Run(
        token=secrets.token_urlsafe(16),
        player_id=player_id,
        name=name,
        rng=random.Random(),
    )
    _runs[run.token] = run
    _deal(run)
    return _state(run)


def submit(token: str, pairs: dict[int, int]) -> dict:
    """Mark a submitted board and either deal the next one or end the run."""
    run = _runs.get(token)
    if run is None or run.over or run.board is None:
        raise UnknownRun(token)

    run.last_seen = time.monotonic()
    board = run.board

    # A human may only be offered one dog, and a dog one human — the same
    # constraint the multiplayer board enforces through exclusive claims.
    if len(set(pairs.values())) != len(pairs):
        raise ValueError("Each dog can only be matched with one person.")
    for human_slot, dog_slot in pairs.items():
        if not 0 <= human_slot < len(board.humans) or not 0 <= dog_slot < len(board.dogs):
            raise ValueError("That isn't a pairing on this board.")

    marks = boards.grade(board, pairs)
    right = sum(1 for ok in marks.values() if ok)
    perfect = boards.is_perfect(board, pairs)

    run.correct += right
    run.boards_played += 1
    if perfect:
        run.perfect_streak += 1
        run.longest_streak = max(run.longest_streak, run.perfect_streak)
    else:
        run.lives -= 1
        run.perfect_streak = 0

    # Safe to reveal now: this board is closed either way.
    result_board = board
    if run.lives <= 0 or _deal(run) is None:
        _finish(run)

    result = _state(run)
    result["wasPerfect"] = perfect
    result["roundCorrect"] = right
    result["marks"] = {str(human): ok for human, ok in marks.items()}
    result["boardAnswer"] = result_board.answer_payload()
    if run.over:
        result["leaderboard"] = store.top(store.BOARD_SOLO_MATCH)
        result["rank"] = store.rank_of(store.BOARD_SOLO_MATCH, run.player_id)
    return result
