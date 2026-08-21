"""Leaderboards — THE STORAGE SEAM.

Scores are kept in memory (so every player sees the same board) and snapshotted
to a small JSON file (so they survive a restart or a redeploy). No database
involved, on purpose: the real DB belongs to another part of the project and may
not even be Postgres.

The file lives in ``$GAME_DATA_DIR`` (default ``data/``, which is ``/app/data``
inside the container — mounted as a named volume by ``docker-compose.yml`` so it
outlives ``docker compose up --build``). Writes are atomic: a temp file in the
same directory, then ``os.replace``, so a crash mid-write can never leave a
truncated board behind.

**Replacing this module.** One row per player per board, already in the shape a
table or a Mongo document wants. Swap ``_load`` / ``_write_now`` for DB reads and
writes; the rest of the package only calls ``record_solo_run``,
``record_multiplayer_result`` and ``top``.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

BOARD_SOLO = "solo"
BOARD_MULTIPLAYER = "multiplayer"
# Mix & Match keeps its own boards: a Streak Survival score counts answers and a
# Mix & Match score counts points, so ranking them together would compare
# numbers that don't mean the same thing.
BOARD_SOLO_MATCH = "solo_match"
BOARD_MULTIPLAYER_MATCH = "multiplayer_match"
BOARDS = (BOARD_SOLO, BOARD_MULTIPLAYER, BOARD_SOLO_MATCH, BOARD_MULTIPLAYER_MATCH)

# Which boards rank by wins (party games) rather than by personal best.
_WIN_RANKED = (BOARD_MULTIPLAYER, BOARD_MULTIPLAYER_MATCH)

DATA_DIR = Path(os.getenv("GAME_DATA_DIR", "data"))
DATA_FILE = DATA_DIR / "leaderboards.json"

# Coalesce bursts of updates into one write, but never drop the last one: a
# trailing timer flushes whatever is still dirty.
MIN_WRITE_INTERVAL = 1.0
MAX_ROWS_PER_BOARD = 500


@dataclass
class Entry:
    """A player's personal best on one board.

    Field names are camelCase because this dataclass is serialised straight to
    JSON for the frontend, the same way ``Match.as_dict`` does it in models.py.
    """

    playerId: str
    name: str
    best: int = 0
    longestStreak: int = 0
    gamesPlayed: int = 0
    wins: int = 0
    updatedAt: str = ""


@dataclass
class _State:
    boards: dict[str, dict[str, Entry]] = field(default_factory=dict)


_lock = threading.Lock()
_state = _State()
_timer: threading.Timer | None = None
_dirty = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> None:
    """Read the snapshot at import. A missing or corrupt file starts empty."""
    for board in BOARDS:
        _state.boards.setdefault(board, {})
    if not DATA_FILE.exists():
        return
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        for board in BOARDS:
            rows = raw.get("boards", {}).get(board, [])
            _state.boards[board] = {
                row["playerId"]: Entry(**{k: v for k, v in row.items() if k in Entry.__annotations__})
                for row in rows
                if "playerId" in row
            }
    except (OSError, ValueError, TypeError) as exc:
        log.warning("leaderboard snapshot unreadable, starting fresh: %s", exc)
        _state.boards = {board: {} for board in BOARDS}


def _write_now() -> None:
    """Atomically replace the snapshot. Called with `_lock` held."""
    global _dirty
    payload = {
        "version": 1,
        "savedAt": _now(),
        "boards": {
            board: [asdict(e) for e in _sorted(board)[:MAX_ROWS_PER_BOARD]] for board in BOARDS
        },
    }
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, DATA_FILE)
        _dirty = False
    except OSError as exc:
        # A read-only or missing volume must not take the game down; scores just
        # stay in memory for this process.
        log.warning("could not persist leaderboards to %s: %s", DATA_FILE, exc)
        _dirty = False


def _mark_dirty() -> None:
    """Schedule a snapshot. Called with `_lock` held."""
    global _timer, _dirty
    _dirty = True
    if _timer is not None:
        return  # a flush is already pending; it will pick this up
    _timer = threading.Timer(MIN_WRITE_INTERVAL, _flush)
    _timer.daemon = True
    _timer.start()


def _flush() -> None:
    global _timer
    with _lock:
        _timer = None
        if _dirty:
            _write_now()


def flush() -> None:
    """Force a snapshot now (used on shutdown)."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        if _dirty:
            _write_now()


def _sorted(board: str) -> list[Entry]:
    entries = list(_state.boards.get(board, {}).values())
    if board in _WIN_RANKED:
        # Wins first — the point of a party game — then best single-game score.
        entries.sort(key=lambda e: (-e.wins, -e.best, e.updatedAt))
    else:
        entries.sort(key=lambda e: (-e.best, -e.longestStreak, e.updatedAt))
    return entries


def _entry(board: str, player_id: str, name: str) -> Entry:
    rows = _state.boards.setdefault(board, {})
    entry = rows.get(player_id)
    if entry is None:
        entry = Entry(playerId=player_id, name=name)
        rows[player_id] = entry
    entry.name = name  # a rename should follow the player
    return entry


def record_solo_run(
    player_id: str,
    name: str,
    correct: int,
    longest_streak: int,
    board: str = BOARD_SOLO,
) -> None:
    """Fold a finished single-player run into one of the solo boards."""
    with _lock:
        entry = _entry(board, player_id, name)
        entry.gamesPlayed += 1
        entry.best = max(entry.best, correct)
        entry.longestStreak = max(entry.longestStreak, longest_streak)
        entry.updatedAt = _now()
        _mark_dirty()


def record_multiplayer_result(
    player_id: str,
    name: str,
    score: int,
    longest_streak: int,
    won: bool,
    board: str = BOARD_MULTIPLAYER,
) -> None:
    """Fold a finished multiplayer game into one of the multiplayer boards."""
    with _lock:
        entry = _entry(board, player_id, name)
        entry.gamesPlayed += 1
        entry.best = max(entry.best, score)
        entry.longestStreak = max(entry.longestStreak, longest_streak)
        entry.wins += 1 if won else 0
        entry.updatedAt = _now()
        _mark_dirty()


def top(board: str, limit: int = 20) -> list[dict]:
    """The board, best first, ready to serialise."""
    with _lock:
        return [asdict(e) for e in _sorted(board)[:limit]]


def rank_of(board: str, player_id: str) -> int | None:
    """1-based rank, or None if the player has never played."""
    with _lock:
        for i, entry in enumerate(_sorted(board), start=1):
            if entry.playerId == player_id:
                return i
    return None


def forget_player(player_id: str) -> int:
    """Drop a player from every board. Returns how many entries went.

    Called when an account is deleted. The boards live in a JSON file rather
    than the database, so nothing cascades here — this is the hand-written
    equivalent, and without it a deleted account keeps its high score forever
    under an id nobody can claim.
    """
    removed = 0
    with _lock:
        for board in BOARDS:
            if _state.boards.get(board, {}).pop(player_id, None) is not None:
                removed += 1
        if removed:
            _mark_dirty()
    return removed


_load()
# On a clean shutdown, write whatever the debounce timer hasn't got to yet.
atexit.register(flush)
