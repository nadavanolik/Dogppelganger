"""Background processing queue for uploaded images — THE PRIORITY SEAM.

Jobs are rows in ``upload_jobs`` (queued -> processing -> done | error). A
small pool of async workers repeatedly claims the highest-priority queued job
and turns it into a breed match via ``predict_breed``.

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
from ..model import predict_breed
from ..models import UploadJob

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
            db.expunge(job)
            return job
        finally:
            db.close()

    assert _claim_lock is not None, "start_workers() must run before workers claim jobs"
    async with _claim_lock:
        return await asyncio.to_thread(_do)


async def _finish(job_id: int, result: dict | None, error: str | None) -> UploadJob | None:
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
                job.breed_name = result["breedName"]
                job.trait = result["trait"]
                job.confidence = result["confidence"]
            job.finished_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            db.expunge(job)
            return job
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
            result = predict_breed(f"{job.id}:{job.original_filename}")
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
