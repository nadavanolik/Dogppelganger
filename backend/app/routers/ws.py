"""Real-time WebSocket endpoint — the backbone for live DMs, notifications,
and multiplayer game state.

This is the foundation: an authenticated connection per user and a manager that
can send to one user or broadcast to everyone. Message routing for specific
features (DMs, `game_action` -> `game_state_update`, etc.) builds on top of it.

Messages are typed JSON events: {"type": "...", "payload": {...}}.

Note: the connection registry is in-memory, so run a single worker. Scaling to
multiple workers later means moving this to Redis pub/sub.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from ..security import decode_token

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
        for ws in list(self.active.get(user_id, set())):
            await ws.send_json(message)

    async def broadcast(self, message: dict) -> None:
        for conns in list(self.active.values()):
            for ws in list(conns):
                await ws.send_json(message)


manager = ConnectionManager()


@router.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    # Authenticate from the token passed as a query param (?token=<jwt>).
    user_id = decode_token(token)
    if user_id is None:
        await ws.close(code=1008)  # policy violation
        return

    await manager.connect(user_id, ws)
    try:
        await manager.send_to_user(user_id, {"type": "connected", "payload": {"userId": user_id}})
        while True:
            event = await ws.receive_json()
            # Placeholder routing: echo to everyone. Replace with real handlers
            # (DM -> send_to_user, game_action -> validate + game_state_update).
            await manager.broadcast({"type": "echo", "payload": event, "from": user_id})
    except WebSocketDisconnect:
        manager.disconnect(user_id, ws)
