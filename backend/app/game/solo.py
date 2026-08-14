"""Single-player Streak Survival.

One human, two dogs, pick the right one. **No timer** — think as long as you
like. Three lives; a wrong answer costs one and resets the streak. The run ends
at zero lives and the score *is* how far you got: total correct answers, with
the longest streak kept as a second stat.

Questions are served one at a time against a run token so the answer key stays
on the server. There is no clock, so plain REST is enough — no WebSocket needed
for this mode.
"""
from __future__ import annotations

import random
import secrets
import time
from dataclasses import dataclass, field

from . import rounds, store
from .rounds import Question

STARTING_LIVES = 3
OPTIONS_PER_QUESTION = 2

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
    streak: int = 0
    longest_streak: int = 0
    asked: int = 0
    used_item_ids: set[str] = field(default_factory=set)
    current: Question | None = None
    over: bool = False
    last_seen: float = field(default_factory=time.monotonic)


_runs: dict[str, Run] = {}


class UnknownRun(Exception):
    """Raised for a token that never existed, expired, or is already finished."""


def _sweep() -> None:
    cutoff = time.monotonic() - RUN_IDLE_TIMEOUT
    for token in [t for t, run in _runs.items() if run.last_seen < cutoff]:
        _runs.pop(token, None)


def _next_question(run: Run) -> Question | None:
    question = rounds.build_question(
        run.asked,
        run.rng,
        options_per=OPTIONS_PER_QUESTION,
        used_item_ids=run.used_item_ids,
    )
    if question is None:
        return None
    run.used_item_ids.add(question.item_id)
    run.asked += 1
    run.current = question
    return question


def _state(run: Run) -> dict:
    return {
        "runToken": run.token,
        "lives": run.lives,
        "score": run.correct,
        "streak": run.streak,
        "longestStreak": run.longest_streak,
        "over": run.over,
        "question": run.current.payload() if run.current and not run.over else None,
    }


def start_run(player_id: str, name: str) -> dict:
    """Begin a run and hand back its first question."""
    _sweep()
    run = Run(
        token=secrets.token_urlsafe(16),
        player_id=player_id,
        name=name,
        rng=random.Random(),
    )
    _runs[run.token] = run
    _next_question(run)
    return _state(run)


def answer(token: str, choice: int) -> dict:
    """Score one answer and either serve the next question or end the run."""
    run = _runs.get(token)
    if run is None or run.over or run.current is None:
        raise UnknownRun(token)

    run.last_seen = time.monotonic()
    question = run.current
    was_right = choice == question.answer

    if was_right:
        run.correct += 1
        run.streak += 1
        run.longest_streak = max(run.longest_streak, run.streak)
    else:
        run.lives -= 1
        run.streak = 0

    if run.lives <= 0:
        run.over = True
        run.current = None
        store.record_solo_run(run.player_id, run.name, run.correct, run.longest_streak)
        _runs.pop(token, None)
    elif _next_question(run) is None:
        # The pool is exhausted (astonishing, but don't hang the client on it).
        run.over = True
        run.current = None
        store.record_solo_run(run.player_id, run.name, run.correct, run.longest_streak)
        _runs.pop(token, None)

    result = _state(run)
    result["wasCorrect"] = was_right
    # Safe to reveal now: this question is closed either way.
    result["answerIndex"] = question.answer
    if run.over:
        result["leaderboard"] = store.top(store.BOARD_SOLO)
        result["rank"] = store.rank_of(store.BOARD_SOLO, run.player_id)
    return result
