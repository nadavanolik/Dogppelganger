"""The game's WebSocket endpoint — THE IDENTITY SEAM.

A separate socket from ``app/routers/ws.py`` on purpose: that one is the shared
backbone for DMs and notifications and is still being built, and the game has no
business editing it. ProjectPlan 2.x wants a single socket per client in the end,
and ``hub.py`` documents the two-line merge that gets there.

**Identity.** Ideally every player is a logged-in user, and this endpoint prefers
that: given ``?token=<jwt>`` it uses the real user id. But the frontend's auth is
still local-only, so it also accepts ``?playerId=&name=``, which is enough to run
a real room with real people today. When login issues real tokens, delete
``_identify``'s fallback branch — nothing else changes.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..security import decode_token
from .hub import Player, hub

log = logging.getLogger(__name__)

router = APIRouter()

MAX_NAME = 24


class SocketRegistry:
    """Which sockets belong to which player (a player may have several tabs)."""

    def __init__(self) -> None:
        self.sockets: dict[str, set[WebSocket]] = {}

    def add(self, player_id: str, ws: WebSocket) -> None:
        self.sockets.setdefault(player_id, set()).add(ws)

    def remove(self, player_id: str, ws: WebSocket) -> bool:
        """Drop one socket; True if that was the player's last one."""
        live = self.sockets.get(player_id)
        if not live:
            return True
        live.discard(ws)
        if not live:
            self.sockets.pop(player_id, None)
            return True
        return False

    async def send(self, player_id: str, message: dict) -> None:
        for ws in list(self.sockets.get(player_id, ())):
            try:
                await ws.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                # Socket died between our check and the write; the disconnect
                # handler will clean it up.
                self.sockets.get(player_id, set()).discard(ws)


registry = SocketRegistry()
hub.bind(registry.send)


def _identify(token: str, player_id: str, name: str) -> Player | None:
    """Work out who is connecting, preferring a real JWT when there is one."""
    if token:
        user_id = decode_token(token)
        if user_id is not None:
            return Player(id=f"u{user_id}", name=(name or f"user{user_id}")[:MAX_NAME])
        return None  # a token was offered and it was bad — don't quietly downgrade

    # TEMPORARY: the frontend's login is local-only, so trust the ids it makes.
    # Delete this branch once /api/auth issues tokens the SPA actually holds.
    player_id = player_id.strip()[:64]
    if not player_id:
        return None
    return Player(id=player_id, name=(name.strip() or "anon")[:MAX_NAME])


@router.websocket("/api/game/ws")
async def game_socket(
    ws: WebSocket,
    token: str = Query(default=""),
    playerId: str = Query(default=""),
    name: str = Query(default=""),
):
    player = _identify(token, playerId, name)
    if player is None:
        await ws.close(code=1008)  # policy violation
        return

    await ws.accept()
    registry.add(player.id, ws)
    await ws.send_json({"type": "connected", "payload": {"playerId": player.id}})

    try:
        while True:
            event = await ws.receive_json()
            if not isinstance(event, dict):
                continue
            await hub.handle(player, event)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("game socket for %s failed", player.id)
    finally:
        last_socket = registry.remove(player.id, ws)
        if last_socket:
            # Only give up their seat once every tab is gone.
            await hub.on_disconnect(player.id)
