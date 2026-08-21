"""The one real-time channel: live DMs, notifications, and upload progress.

One authenticated socket per logged-in client, opened once after login and
reused everywhere — which is what ProjectPlan asks for, and what the SPA now
does. There used to be a second socket at `/api/uploads/ws` keyed by a
client-supplied owner string; it has been folded in here, because two
registries doing the same job with different identity rules is one more than
necessary.

**Server -> client only.** Nothing inbound is routed: a direct message is
persisted by `POST /api/dm/...` and only then pushed, so there is exactly one
path that writes to the database. That also means a message is never lost
because a socket was flapping when it was sent. Inbound frames are read purely
to keep the connection alive and to notice when it closes.

Event types pushed from here:

    upload_update   a job of yours changed status (queued -> done | error)
    dm_received     someone sent you a message
    dm_sent         you sent a message from another tab
    dm_read         the other participant read your messages
    notification    a bell notification was created for you

Note: the connection registry is in-memory, so run a single worker. Scaling to
multiple workers later means moving this to Redis pub/sub.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..models import User
from ..security import decode_media_token, decode_token_claims

log = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> set of that user's live sockets (they may have several tabs)
        self.active: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.active.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        conns = self.active.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self.active.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        """Push to every tab this user has open.

        Each write is guarded: a socket can die between the lookup and the
        send, and without the guard one dead tab would abort the loop and every
        later recipient would silently miss the frame.
        """
        for ws in list(self.active.get(user_id, ())):
            try:
                await ws.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                self.active.get(user_id, set()).discard(ws)

    async def broadcast(self, message: dict) -> None:
        for user_id in list(self.active):
            await self.send_to_user(user_id, message)

    async def disconnect_user(self, user_id: int) -> None:
        """Drop every socket a user has — used when their account is deleted,
        so a connection authenticated a minute ago stops receiving pushes for
        a row that no longer exists."""
        for ws in list(self.active.get(user_id, ())):
            try:
                await ws.close(code=1008)
            except (RuntimeError, WebSocketDisconnect):
                pass
        self.active.pop(user_id, None)


manager = ConnectionManager()


def user_for_token(token: str) -> User | None:
    """Resolve a socket's `?token=`, accepting either token kind.

    A browser cannot set headers on a WebSocket handshake, so the token has to
    ride in the query string — where it lands in nginx's access log. The SPA
    therefore sends the short-lived media-scoped token; the session token is
    accepted too so that a test or a script does not need two tokens to open
    one socket.
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
        return user


@router.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    user = user_for_token(token)
    if user is None:
        await ws.close(code=1008)  # policy violation
        return
    user_id = user.id

    await manager.connect(user_id, ws)
    try:
        await manager.send_to_user(user_id, {"type": "connected", "payload": {"userId": user_id}})
        while True:
            # receive_text, not receive_json: the client sends a bare "ping"
            # string as a keep-alive (nginx closes idle proxied connections at
            # 60s), and receive_json would raise on it and kill the connection.
            raw = await ws.receive_text()
            if raw == "ping":
                continue
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(event, dict):
                continue
            # Nothing inbound is routed today — see the module docstring. The
            # game keeps its own socket at /api/game/ws; merging it here is a
            # documented follow-up in app/game/hub.py, deliberately not done
            # now because it changes what "the player's last socket closed"
            # means once the socket is open app-wide rather than per room.
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("socket for user %s failed", user_id)
    finally:
        # In `finally`, not in the except branch: any other exception would
        # otherwise leave the socket registered forever and every later push to
        # this user would try to write to a dead connection.
        manager.disconnect(user_id, ws)
