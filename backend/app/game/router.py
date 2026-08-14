"""REST endpoints for the games. Mounted at /api/game.

Split of responsibilities: anything with a clock or shared state goes over the
WebSocket (``ws.py``), and everything else — lobby discovery, the untimed solo
run, leaderboards — is plain REST, because it is easier to read, easier to debug
in /api/docs, and matches ProjectPlan 2.8/2.9.

``playerId``/``playerName`` travel in request bodies for the same reason
``ws.py`` accepts them as query params: the SPA's login is still local-only. See
the identity seam note there.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import solo, solo_match, store
from .hub import hub
from .rooms import GAME_DOUBLE, GAME_TYPES, MATCH_SECONDS_CHOICES, ROUNDS_CHOICES, SECONDS_CHOICES

router = APIRouter(prefix="/api/game", tags=["game"])


class PlayerRef(BaseModel):
    playerId: str = Field(min_length=1, max_length=64)
    playerName: str = Field(default="anon", max_length=24)


class CreateRoom(PlayerRef):
    name: str = Field(default="", max_length=60)
    gameType: str = Field(default=GAME_DOUBLE)


class SoloAnswer(BaseModel):
    runToken: str
    choice: int


class SoloBoard(BaseModel):
    runToken: str
    # human slot -> dog slot. JSON object keys arrive as strings.
    pairs: dict[int, int] = Field(default_factory=dict)


def _room_summary(room) -> dict:
    host = room.members.get(room.host_id)
    return {
        "id": room.id,
        "code": room.code,
        "name": room.name,
        "gameType": room.game_type,
        "phase": room.phase,
        "hostName": host.name if host else "—",
        "playerCount": len(room.connected_members),
        "roundsTotal": room.rounds_total,
        "secondsPerQuestion": room.seconds_per_question,
    }


# ------------------------------------------------------------------- lobbies


@router.get("/rooms")
async def list_rooms():
    """Open rooms, newest first — the public lobby list."""
    return {
        "rooms": [_room_summary(r) for r in hub.rooms.open_rooms()],
        "options": {
            "rounds": list(ROUNDS_CHOICES),
            "seconds": list(SECONDS_CHOICES),
            "matchSeconds": list(MATCH_SECONDS_CHOICES),
            "gameTypes": list(GAME_TYPES),
        },
    }


@router.post("/rooms", status_code=201)
async def create_room(data: CreateRoom):
    """Create a room and become its host.

    The creator is not a member yet — they join over the WebSocket, same as
    everyone else, so there is only one code path for membership.
    """
    try:
        room = hub.rooms.create(data.name, data.playerId, data.playerName, data.gameType)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return _room_summary(room)


@router.get("/rooms/by-code/{code}")
async def room_by_code(code: str):
    """Resolve a typed-in join code to a room."""
    room = hub.rooms.by_code(code)
    if room is None:
        raise HTTPException(404, "No room with that code.")
    return _room_summary(room)


@router.get("/rooms/{room_id}")
async def room_state(room_id: str):
    """Full room state, for a client that hasn't opened its socket yet."""
    room = hub.rooms.get(room_id)
    if room is None:
        raise HTTPException(404, "That room doesn't exist any more.")
    return hub.rooms.state(room)


# ---------------------------------------------------------------------- solo


@router.post("/solo/start")
async def solo_start(data: PlayerRef):
    """Begin a Streak Survival run and get its first question."""
    return solo.start_run(data.playerId, data.playerName)


@router.post("/solo/answer")
async def solo_answer(data: SoloAnswer):
    """Answer the current question; get the verdict and the next one."""
    try:
        return solo.answer(data.runToken, data.choice)
    except solo.UnknownRun:
        raise HTTPException(404, "That run has finished or expired — start a new one.")


@router.post("/solo/match/start")
async def solo_match_start(data: PlayerRef):
    """Begin a Mix & Match run and get its first board."""
    return solo_match.start_run(data.playerId, data.playerName)


@router.post("/solo/match/submit")
async def solo_match_submit(data: SoloBoard):
    """Submit a finished board; get it marked and the next one dealt."""
    try:
        return solo_match.submit(data.runToken, data.pairs)
    except solo_match.UnknownRun:
        raise HTTPException(404, "That run has finished or expired — start a new one.")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


# --------------------------------------------------------------- leaderboards


@router.get("/leaderboard/{board}")
async def leaderboard(board: str, limit: int = 20):
    """Top scores. `board` is 'solo' or 'multiplayer'."""
    if board not in store.BOARDS:
        raise HTTPException(404, f"Unknown board '{board}'.")
    return {"board": board, "entries": store.top(board, max(1, min(limit, 100)))}
