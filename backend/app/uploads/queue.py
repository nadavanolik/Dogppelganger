"""Background processing queue for uploaded images — THE PRIORITY SEAM.

Jobs are rows in ``upload_jobs`` (queued -> processing -> done | error). A
small pool of async workers repeatedly claims the highest-priority queued job
and matches its stored photo against the dog corpus via ``model.match_dog``.

``priority_key`` is the only thing that decides processing order, and today
it's a placeholder: pure arrival order (lower id = uploaded earlier = goes
first). The real scheme this project wants eventually — urgent jobs jump the
line, smaller/faster images first, fairness so one owner's 100-image batch
can't starve everyone else — isn't decided yet. Replace this one function
later; nothing else in this module needs to change.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Awaitable, Callable

from ..database import SessionLocal
from ..model import DogMatchResult, match_dog
from ..models import UploadJob
from ..storage import layout

log = logging.getLogger(__name__)

Notify = Callable[[str, dict], Awaitable[None]]

WORKER_COUNT = 3
IDLE_POLL_SECONDS = 0.5
# Fake "doing work" latency so status transitions are visible instead of
# instant, and so swapping in a real model later has an obvious place to go.
MIN_PROCESS_SECONDS = 1.0
MAX_PROCESS_SECONDS = 2.5

# Guards the claim step so two workers can never grab the same queued job.
# Created in start_workers(), not here — a Lock binds to whatever event loop
# is running when it's first awaited, and the app's loop is a fresh one each
# time start_workers() runs (e.g. once per test's TestClient).
_claim_lock: asyncio.Lock | None = None

_tasks: list[asyncio.Task] = []


def priority_key(job: UploadJob) -> tuple:
    """Lower sorts first. Placeholder: pure arrival order."""
    return (job.id,)


def _event(job: UploadJob) -> dict:
    return {"type": "upload_update", "payload": job.as_dict()}


def _detach(db, job: UploadJob) -> UploadJob:
    """Take a job out of its session with everything ``as_dict()`` needs loaded.

    Workers report jobs over the WebSocket *after* the session that produced
    them is closed, so the ``dog`` relationship has to be resolved while it can
    still be queried. Touching it here forces the lazy load; skip that and
    ``as_dict()`` raises DetachedInstanceError — which ``_notify`` swallows, so
    the client silently never hears that its match is ready.

    This bites even when there is no dog yet: a detached instance refuses the
    lazy load rather than short-circuiting on the NULL foreign key.
    """
    dog = job.dog
    db.expunge(job)
    if dog is not None:
        db.expunge(dog)
    return job


async def _claim_next() -> UploadJob | None:
    """Atomically move the next queued job to 'processing' and hand it back."""

    def _do() -> UploadJob | None:
        db = SessionLocal()
        try:
            queued = db.query(UploadJob).filter(UploadJob.status == "queued").all()
            if not queued:
                return None
            job = min(queued, key=priority_key)
            job.status = "processing"
            db.commit()
            db.refresh(job)
            return _detach(db, job)
        finally:
            db.close()

    assert _claim_lock is not None, "start_workers() must run before workers claim jobs"
    async with _claim_lock:
        return await asyncio.to_thread(_do)


def _run_model(job_id: int) -> DogMatchResult:
    """Match one job's photo against the corpus. Blocking — call in a thread.

    Reads the stored, already-normalised original (never the client's bytes),
    so the model sees the same RGB JPEG whatever the browser sent.
    """
    db = SessionLocal()
    try:
        return match_dog(db, layout.upload_path(job_id, "orig"))
    finally:
        db.close()


async def _finish(job_id: int, result: DogMatchResult | None, error: str | None) -> UploadJob | None:
    def _do() -> UploadJob | None:
        db = SessionLocal()
        try:
            job = db.get(UploadJob, job_id)
            if job is None:
                return None
            if error is not None:
                job.status = "error"
                job.error = error[:300]
            else:
                job.status = "done"
                job.dog_asset_id = result.dog_asset_id
                job.score = result.score
                job.shared_traits = result.shared_traits
            job.finished_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return _detach(db, job)
        finally:
            db.close()

    return await asyncio.to_thread(_do)


async def _notify(notify: Notify, job: UploadJob) -> None:
    try:
        await notify(job.owner_id, _event(job))
    except Exception:
        # A dead/never-open socket must not take a worker down with it.
        log.debug("could not notify owner %s of job %s", job.owner_id, job.id)


async def _worker(notify: Notify) -> None:
    while True:
        job = await _claim_next()
        if job is None:
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue

        await _notify(notify, job)
        try:
            await asyncio.sleep(random.uniform(MIN_PROCESS_SECONDS, MAX_PROCESS_SECONDS))
            # Off the event loop: matching is synchronous DB + file work, and
            # the real model will be CPU-heavy on top of that.
            result = await asyncio.to_thread(_run_model, job.id)
            done = await _finish(job.id, result, None)
        except Exception as exc:  # a broken job shouldn't take the worker down
            log.exception("upload job %s failed", job.id)
            done = await _finish(job.id, None, str(exc))

        if done is not None:
            await _notify(notify, done)


def start_workers(notify: Notify) -> None:
    """Spawn the worker pool. Call once, at app startup."""
    global _claim_lock
    _claim_lock = asyncio.Lock()
    for _ in range(WORKER_COUNT):
        _tasks.append(asyncio.create_task(_worker(notify)))


async def stop_workers() -> None:
    """Cancel the worker pool. Call once, at app shutdown."""
    global _claim_lock
    for task in _tasks:
        task.cancel()
    for task in _tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _tasks.clear()
    _claim_lock = None
