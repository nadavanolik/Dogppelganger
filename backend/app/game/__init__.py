"""The game: single-player Streak Survival and Kahoot-style multiplayer rooms.

This package is deliberately self-contained — it imports nothing from
``app.models`` or ``app.database``, so it neither depends on nor conflicts with
the database work happening elsewhere in the backend. All game state lives in
memory; the only thing written to disk is the leaderboard snapshot in
``store.py``.

Four seams connect it to the rest of the app. Each is one small edit when the
surrounding features land:

1. ``content.py`` — where rounds come from (today: deterministic dummies).
2. ``store.py``   — where leaderboards persist (today: a JSON file).
3. ``ws.py``      — who a player is (today: JWT if present, else a query param).
4. ``hub.py``     — how a message reaches a player (today: our own registry).

Nothing else in the package knows about transport, identity, or storage.

``router`` below bundles the REST endpoints and the WebSocket route together, so
wiring the whole feature into the app is a single ``include_router`` call.
"""
from fastapi import APIRouter

from .router import router as _rest_router
from .ws import router as _ws_router

router = APIRouter()
router.include_router(_rest_router)
router.include_router(_ws_router)

__all__ = ["router"]
