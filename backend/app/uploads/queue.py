"""Background processing queue for uploaded images — THE PRIORITY SEAM.

Jobs are rows in ``upload_jobs`` (queued -> processing -> done | error). A
pool of async workers, sized to the machine's CPU count, repeatedly claims
the highest-priority queued job and matches its stored photo against the dog
corpus via ``model.match_dog``.

**The scheduling algorithm: Weighted Start-time Fair Queueing**, adapted from
Goyal, Vin & Cheng, "Start-time Fair Queueing: A Scheduling Algorithm for
Integrated Services Packet Switching Networks" (SIGCOMM 1996) — the family of
algorithms (Fair Queueing, WFQ, Deficit Round Robin) network routers use to
share one output link fairly among many flows. That is exactly this problem:
many owners ("flows") share a small worker pool ("the link"), submit
variable-size jobs ("packets"), and no owner may starve another regardless of
how many jobs they send.

Each owner gets a virtual clock (``_vt``). Claiming one of their jobs advances
their clock by that job's estimated cost; whichever owner's clock currently
reads earliest goes next. An owner *newly (re)joining* the backlog — nothing
of theirs was queued a moment ago — has their clock pulled up to the current
global clock (``_global_vt``) before they're considered; an owner who has
been backlogged continuously keeps their real clock, even where it reads
behind the global one, because that is exactly an owner who is legitimately
due a turn. The reset is straight out of the paper, and is what stops a fresh
or returning owner from "stealing" the queue with a stale low tag — clamping
*every* owner on *every* claim would look similar but is wrong: it would
erase the "who's most behind" signal the whole algorithm runs on. This is
also what makes one owner's 100-image batch unable to starve everyone else:
every *other* active owner is guaranteed a turn within one rotation,
independent of how deep anyone's backlog is.

Urgent jobs get weight, not an absolute override, in two places:

* Within one owner's own backlog, urgent jobs are simply picked first.
* Across owners, one currently holding an urgent job gets a bounded discount
  on their clock (``URGENT_DISCOUNT_SECONDS``) — enough to usually jump other
  owners' ordinary work, but a fixed constant, not proportional to anything.
  An owner who is genuinely further behind still wins. That cap is what keeps
  "mark everything urgent" from being able to starve anyone: the worst extra
  delay it can inflict on somebody else is bounded, not unbounded.

Aging (``AGING_PER_SECOND``) closes the one gap the paper's guarantee doesn't
cover: it guarantees fairness *between* owners, not the order *within* one
owner's own queue. Without it, an owner who keeps adding new small photos
could leave an old large photo of their own stuck behind an endless stream of
newer, "cheaper" siblings forever — so a queued job's effective cost shrinks
the longer it has waited, until even a large photo eventually wins.

See ``_select_next`` for the implementation and ``estimate_cost`` for why
byte size — not raw upload order — approximates a job's processing cost.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime
from typing import Awaitable, Callable

from ..database import SessionLocal
from ..model import DogMatchResult, match_dog
from ..models import UploadJob
from ..storage import layout

log = logging.getLogger(__name__)

Notify = Callable[[int, dict], Awaitable[None]]

# One worker per core: each worker holds a face detector plus a CLIP session
# pinned to a single onnxruntime thread (app/ml/encoder.py, deliberately, so
# N workers oversubscribe nothing), so N workers on N cores is full use of
# the machine with no contention between them. Capped well under the DB
# pool's default ceiling (SQLAlchemy: 5 + 10 overflow) so a big machine can't
# starve the connection pool instead of the CPU. Overridable for tuning.
WORKER_COUNT = int(os.getenv("UPLOAD_WORKER_COUNT", str(min(os.cpu_count() or 3, 8))))
IDLE_POLL_SECONDS = 0.5
# Fake "doing work" latency on top of the real model, purely so status
# transitions stay visible instead of instant in a demo.
MIN_PROCESS_SECONDS = 1.0
MAX_PROCESS_SECONDS = 2.5

# ------------------------------------------------------- the cost model
#
# BASE_COST_SECONDS is the part every job pays alike (face detector + CLIP +
# corpus match); BYTES_PER_SECOND turns the stored photo's byte size into the
# variable part (see `estimate_cost`). Both are a starting guess, not a
# measurement — recalibrate against real wall-clock times once deployed.
BASE_COST_SECONDS = 0.4
BYTES_PER_SECOND = 1_000_000

# ------------------------------------------------------- fairness knobs
#
# An urgent job "costs" a quarter as much of its owner's virtual clock, so
# that owner's next turn comes back around sooner.
URGENT_WEIGHT = 4.0
# Bounded head start, in seconds of virtual clock, for an owner currently
# holding an urgent job — real cross-owner weight, but capped: an owner who
# is genuinely further behind still wins, which is what keeps this from ever
# starving anyone.
URGENT_DISCOUNT_SECONDS = 3.0
# A queued job's effective cost shrinks by this much per second waited, so a
# large photo can't be stuck forever behind an endless stream of its own
# owner's newer, smaller uploads.
AGING_PER_SECOND = 0.05

# Guards the claim step so two workers can never grab the same queued job,
# and so the fairness state below only ever changes from one place at a time.
# Created in start_workers(), not here — a Lock binds to whatever event loop
# is running when it's first awaited, and the app's loop is a fresh one each
# time start_workers() runs (e.g. once per test's TestClient).
_claim_lock: asyncio.Lock | None = None

_tasks: list[asyncio.Task] = []

# Per-owner virtual clock (the SFQ "start tag" of that owner's last-served
# job) and the global clock it is measured against. In-memory and reset on
# restart — the same tradeoff already accepted for `_claim_lock`: fairness
# bookkeeping resets, but no job is ever lost, because the database, not this
# dict, is what a job actually lives in.
_vt: dict[int, float] = {}
_global_vt: float = 0.0

# Which owners had a queued job as of the *previous* claim — see
# `_select_next`. The reset-to-global-clock rule must fire only for an owner
# newly (re)joining the backlog, never for one who has been in it continuously
# — that second case is exactly an owner who is legitimately behind, and
# clamping them up every round would erase the "who's most behind" signal the
# whole algorithm runs on.
_backlogged: set[int] = set()


def _reset_fairness_state() -> None:
    """Drop the virtual clocks. Called at every `start_workers()` — a fresh
    process starts fairness bookkeeping fresh, same as a real restart would —
    and by tests, so one test's queue traffic can't bias another's."""
    global _global_vt
    _vt.clear()
    _backlogged.clear()
    _global_vt = 0.0


def estimate_cost(job: UploadJob) -> float:
    """Rough seconds to process one job — the queue's only notion of "size".

    Tracing the real pipeline (app/ml) shows only face detection scales with
    the input image, and it runs on the stored "orig" derivative, which the
    upload endpoint already caps at 1024px on its long side; everything after
    cropping — the CLIP encode (resized to a fixed 224x224 first) and the
    matrix match against the corpus — costs the same regardless of the source
    photo. Every derivative is re-encoded as a JPEG at one fixed quality
    (app/storage/imaging.py), so byte size tracks pixel count closely enough
    to use directly, with no second pass over the file just to measure it.

    `byte_size` is measured off the file the worker actually reads, never
    trusted from the client's multipart headers, so a mislabeled upload can't
    game its own priority.
    """
    return BASE_COST_SECONDS + (job.byte_size or 0) / BYTES_PER_SECOND


def _job_weight(job: UploadJob) -> float:
    return URGENT_WEIGHT if job.urgent else 1.0


def _select_next(queued: list[UploadJob]) -> UploadJob:
    """Weighted Start-time Fair Queueing: which queued job goes next.

    See the module docstring for the algorithm and its citation. This is the
    only function that decides order; everything else here just calls it.
    """
    global _global_vt

    by_owner: dict[int, list[UploadJob]] = {}
    for job in queued:
        by_owner.setdefault(job.owner_id, []).append(job)

    # An owner newly (re)joining the backlog since the last claim starts no
    # earlier than the current global clock — otherwise a stale low tag would
    # let them jump everyone the moment they (re)appear (Goyal, Vin & Cheng,
    # 1996). An owner who has been backlogged continuously keeps their real
    # clock, even below the global one — that is precisely an owner who is
    # legitimately behind, and is who the whole algorithm exists to favour.
    for owner_id in by_owner:
        if owner_id not in _backlogged:
            _vt[owner_id] = max(_vt.get(owner_id, 0.0), _global_vt)

    def owner_key(owner_id: int) -> tuple[float, int]:
        has_urgent = any(j.urgent for j in by_owner[owner_id])
        discount = URGENT_DISCOUNT_SECONDS if has_urgent else 0.0
        return (_vt.get(owner_id, 0.0) - discount, owner_id)  # id only breaks exact ties

    owner_id = min(by_owner, key=owner_key)
    start = _vt.get(owner_id, 0.0)

    def job_key(job: UploadJob) -> tuple:
        waited = (datetime.utcnow() - job.created_at).total_seconds() if job.created_at else 0.0
        aged_cost = max(0.0, estimate_cost(job) - AGING_PER_SECOND * waited)
        return (0 if job.urgent else 1, aged_cost, job.id)

    job = min(by_owner[owner_id], key=job_key)

    _vt[owner_id] = start + estimate_cost(job) / _job_weight(job)
    _global_vt = max(_global_vt, start)
    _backlogged.clear()
    _backlogged.update(by_owner)
    return job


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
            job = _select_next(queued)
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
        # The claim needs its own guard: it is outside the try below, so a
        # database blip (Postgres restart, a lock, a schema that hasn't been
        # migrated) used to propagate out of the worker and end the task. All
        # three workers hit it within one poll cycle, and because `_tasks`
        # keeps a strong reference forever, asyncio never reports the dead
        # task — the queue just silently stopped, /api/health stayed green,
        # and every upload sat at "queued" for good.
        try:
            job = await _claim_next()
        except Exception:
            log.exception("could not claim the next upload job; retrying")
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue

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
    _reset_fairness_state()
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
