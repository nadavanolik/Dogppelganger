"""Push notifications for upload jobs. Mounted at /api/uploads/ws.

Server -> client only: whenever a job's status changes (queued -> processing
-> done | error), whoever owns it gets an `upload_update` event immediately,
so the upload panel updates live with no polling or page refresh. There's no
client -> server traffic to route, so unlike app/game this needs no hub —
just a registry to send to.

Same identity seam as app/game/ws.py: `ownerId` is a client-supplied string
because the SPA's login is still local-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter()

MAX_OWNER_ID = 64


class UploadNotifier:
    """Which sockets belong to which owner (they may have several tabs)."""

    def __init__(self) -> None:
        self.sockets: dict[str, set[WebSocket]] = {}

    def add(self, owner_id: str, ws: WebSocket) -> None:
        self.sockets.setdefault(owner_id, set()).add(ws)

    def remove(self, owner_id: str, ws: WebSocket) -> None:
        live = self.sockets.get(owner_id)
        if not live:
            return
        live.discard(ws)
        if not live:
            self.sockets.pop(owner_id, None)

    async def send(self, owner_id: str, message: dict) -> None:
        for ws in list(self.sockets.get(owner_id, ())):
            try:
                await ws.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                # Socket died between our check and the write; the disconnect
                # handler below will clean it up.
                self.sockets.get(owner_id, set()).discard(ws)


notifier = UploadNotifier()


@router.websocket("/api/uploads/ws")
async def uploads_socket(ws: WebSocket, ownerId: str = Query(default="")):
    owner_id = ownerId.strip()[:MAX_OWNER_ID]
    if not owner_id:
        await ws.close(code=1008)  # policy violation
        return

    await ws.accept()
    notifier.add(owner_id, ws)
    try:
        while True:
            # Nothing meaningful arrives from the client; this just keeps the
            # socket open and lets a keep-alive ping pass through harmlessly.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notifier.remove(owner_id, ws)
