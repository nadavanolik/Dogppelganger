"""Direct messages: private 1:1 threads with saved, retrievable history.

Three pieces:
* ``service.py``     — the conversation invariant and the unread counting.
* ``attachments.py`` — sniffing, storing and validating an image or a video.
* ``router.py``      — the REST surface at ``/api/dm``.

**Messages are sent over REST, not over the WebSocket.** ProjectPlan allows
either. REST wins here for three reasons: there is exactly one code path that
writes to the database, it keeps working while a socket is reconnecting, and it
is testable with `TestClient` without a WebSocket dance. The socket
(``app/routers/ws.py``) is a pure push channel — the message is a row before it
is ever a frame.

That also answers "what happens if the recipient is offline", and the answer is
"nothing special": the push finds no sockets and does nothing, and the message
is waiting in their inbox — with an unread count — the next time they look.
"""
from .router import router

__all__ = ["router"]
