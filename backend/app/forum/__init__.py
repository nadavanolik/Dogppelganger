"""The forum: sharing a finished dog photo with a caption, likes, comments.

Same identity seam as app/uploads: ``authorId``/``userId`` are client-supplied
strings, not a real login, because the SPA's auth is still local-only.

* ``router.py`` — REST: create/list posts, comment, react, and the "which of
  my finished dogs can I still share" picker.
* ``seed.py``   — cold-seeding a few fake authors + posts so the forum isn't
  empty on a fresh database.
"""
from .router import router

__all__ = ["router"]
