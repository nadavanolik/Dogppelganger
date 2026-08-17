"""Where image bytes live on disk, and how they get there safely.

Two callers, two very different jobs:

* ``layout`` — the directory contract shared by the ingest script, the upload
  router and docker-compose. Nothing else should build these paths by hand.
* ``imaging`` — decode/normalise/resize. Every image the app stores goes
  through here, which is what guarantees EXIF is gone and the bytes on disk
  were written by Pillow rather than supplied by a client.

See DATA_STORAGE.md §2-3 for why dog photos and user photos are stored and
served so differently.
"""
