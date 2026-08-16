"""Multi-image upload + priority queue: turn a batch of photos into dogs.

Three pieces:
* ``router.py`` — REST: upload files, list your jobs, fetch a job's image.
* ``queue.py``  — the background worker pool that turns queued jobs into
  finished matches (or errors). See its docstring for the priority seam —
  today's ordering is a placeholder that later gets replaced.
* ``ws.py``     — pushes an ``upload_update`` event to whoever owns a job
  whenever its status changes, so the client updates live with no polling.

Identity here is the same seam as ``app/game``: a client-supplied ``ownerId``
string, not a real login, because the SPA's auth is still local-only.
"""
from fastapi import APIRouter

from .router import router as _rest_router
from .ws import router as _ws_router

router = APIRouter()
router.include_router(_rest_router)
router.include_router(_ws_router)

__all__ = ["router"]
