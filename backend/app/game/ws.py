"""The game's WebSocket endpoint — THE IDENTITY SEAM.

A separate socket from ``app/routers/ws.py`` on purpose: that one is the shared
backbone for DMs and notifications and is still being built, and the game has no
business editing it. ProjectPlan 2.x wants a single socket per client in the end,
and ``hub.py`` documents the two-line merge that gets there.

**Identity.** Every player is a logged-in user. Connect with ``?token=<jwt>``
and nothing else; an absent, malformed or stale token closes the socket. The
``?playerId=&name=`` fallback that used to live here — where the server took the
browser's word for who was playing — is gone, which is what the note in this
docstring used to promise would happen "when login issues real tokens".

The token goes in the query string because a browser cannot set headers on a
WebSocket handshake. It is the short-lived media-scoped token rather than the
24-hour session token, so what ends up in nginx's access log expires in minutes
and cannot be replayed against the REST API.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..models import User
from ..security import decode_media_token, decode_token_claims
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


def player_for_token(token: str) -> Player | None:
    """The logged-in user behind a token, as the game's Player value.

    Accepts either token kind so the SPA can reuse whichever it has to hand.
    The player id is ``str(user.id)`` — one canonical mapping, so the frontend
    can compare against ``String(me.id)`` without knowing a prefix convention.
    (It used to be ``f"u{user_id}"``, which meant every comparison site had to
    know about the "u".)

    A plain `SessionLocal()` rather than the `get_db` dependency: FastAPI does
    not run request-scoped dependencies for a WebSocket handshake the way it
    does for a request, and the name has to come from the database.
    """
    if not token:
        return None
    claims = decode_token_claims(token) or decode_media_token(token)
    if claims is None:
        return None
    user_id, token_version = claims
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.token_version != token_version:
            return None
        return Player(id=str(user.id), name=user.username[:MAX_NAME])


@router.websocket("/api/game/ws")
async def game_socket(ws: WebSocket, token: str = Query(default="")):
    player = player_for_token(token)
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
