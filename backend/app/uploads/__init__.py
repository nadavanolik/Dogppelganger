"""Multi-image upload + priority queue: turn a batch of photos into dogs.

Two pieces:
* ``router.py`` — REST: upload files, list your jobs, fetch a job's image,
  share a finished match to the public gallery.
* ``queue.py``  — the background worker pool that turns queued jobs into
  finished matches (or errors). See its docstring for the priority seam —
  today's ordering is a placeholder that later gets replaced.

There used to be a third: a `ws.py` that pushed `upload_update` events over its
own socket at ``/api/uploads/ws``, keyed by a client-supplied owner string. It
is gone. The events now go out over the single authenticated socket in
``app/routers/ws.py``, keyed by the real user id — one connection per client,
one registry, one identity rule. The queue still pushes through the same
``Notify`` seam, so nothing about the worker changed.

Every photo belongs to a real user row: ``UploadJob.owner_id`` is a foreign key
into ``users``, and the server takes it from the caller's token.
"""
from .router import router

__all__ = ["router"]
