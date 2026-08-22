"""Upload -> store -> match, over the real API.

What these assert is the *contract around* the model: that a photo is sanitised
and stored before anything looks at it, that a match names a real row of
`dog_assets`, and that an empty or un-embedded corpus fails loudly instead of
showing a blank card. The matching arithmetic itself is covered in test_ml.py.

Tests that need a working matcher use the `matcher` fixture, which builds one
over a synthetic corpus with a 6KB stand-in encoder — CLIP's 350MB export is
gitignored and CI does not have it.
"""
import base64
import time
from datetime import datetime

import pytest
from conftest import make_image

from app.storage import layout


def _upload(client, owner, files, urgent="[]"):
    """Upload as `owner` — a dict from the `user_factory` fixture.

    There is no `ownerId` field any more: the photo belongs to whoever the
    token says is calling, so the owner is proved rather than asserted.
    """
    return client.post(
        "/api/uploads",
        data={"urgent": urgent},
        files=files,
        headers=owner["headers"],
    )


def one_image(name="me.jpg", **kwargs):
    return [("files", (name, make_image(**kwargs), "image/jpeg"))]


def _b64(**kwargs) -> str:
    """A real encoded image, base64'd — what POST /api/match now expects."""
    return base64.b64encode(make_image(**kwargs)).decode()


# ------------------------------------------------------------------ storing


def test_an_uploaded_photo_is_stored_re_encoded_with_its_facts_recorded(client, user):
    res = _upload(client, user, one_image(width=800, height=600))

    assert res.status_code == 201
    [job] = res.json()["created"]
    assert job["width"] == 800 and job["height"] == 600
    assert job["byteSize"] > 0, "the queue orders on this, so it must be measured"

    for size in layout.UPLOAD_SIZES:
        assert layout.upload_path(job["id"], size).exists(), f"{size} was not written"
    # 512 is the display cap; the 800px source must have come down to it.
    from PIL import Image

    with Image.open(layout.upload_path(job["id"], "display")) as display:
        assert max(display.size) == 512


def test_a_sideways_photo_is_stored_upright(client, user):
    """EXIF orientation is applied at ingest, so nothing downstream — the
    model included — has to know the tag exists."""
    res = _upload(client, user, one_image(width=800, height=600, exif=True))

    [job] = res.json()["created"]
    assert (job["width"], job["height"]) == (600, 800)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(b"MZ\x90\x00" + b"\x00" * 500, "only PNG and JPG", id="a renamed executable"),
        pytest.param(b"\xff\xd8\xff" + b"\x00" * 500, "readable image", id="jpeg magic, junk body"),
    ],
)
def test_a_file_that_isnt_really_an_image_is_rejected(client, user, payload, expected):
    res = _upload(client, user, [("files", ("evil.jpg", payload, "image/jpeg"))])

    assert res.status_code == 201, "a bad file in the batch doesn't fail the request"
    body = res.json()
    assert body["created"] == []
    assert expected in body["rejected"][0]["reason"]


def test_a_rejected_file_leaves_no_job_behind(client, user):
    """The second magic-bytes case gets past the sniff and dies at decode —
    the path where a row could plausibly be orphaned."""
    _upload(client, user, [("files", ("evil.jpg", b"\xff\xd8\xff" + b"\x00" * 500, "image/jpeg"))])

    assert client.get("/api/uploads", headers=user["headers"]).json() == []


def test_a_batch_bigger_than_the_cap_is_refused(client, user):
    files = [("files", (f"{i}.jpg", make_image(64, 64), "image/jpeg")) for i in range(25)]

    res = _upload(client, user, files)

    assert res.status_code == 422
    assert "at most" in res.json()["detail"]


def test_a_good_file_still_lands_when_a_sibling_is_junk(client, user):
    files = [
        ("files", ("good.jpg", make_image(200, 200), "image/jpeg")),
        ("files", ("bad.jpg", b"nope", "image/jpeg")),
    ]

    body = _upload(client, user, files).json()

    assert len(body["created"]) == 1 and len(body["rejected"]) == 1


# ------------------------------------------------------------------ serving


def test_a_photo_is_only_served_to_its_owner(client, user, other_user):
    [job] = _upload(client, user, one_image()).json()["created"]

    mine = client.get(f"/api/uploads/{job['id']}/image", headers=user["headers"])
    theirs = client.get(f"/api/uploads/{job['id']}/image", headers=other_user["headers"])
    anonymous = client.get(f"/api/uploads/{job['id']}/image")

    assert mine.status_code == 200
    assert theirs.status_code == 404, "someone else's photo must not be reachable"
    assert anonymous.status_code == 404, "and neither must a logged-out one"


def test_uploaded_photos_are_never_cached(client, user):
    """Personal data, unlike the dog corpus, must not sit in a shared cache."""
    [job] = _upload(client, user, one_image()).json()["created"]

    res = client.get(f"/api/uploads/{job['id']}/image", headers=user["headers"])

    assert res.headers["cache-control"] == "private, no-store"


def test_the_full_resolution_original_is_not_servable(client, user):
    """`orig` is the model's input; there's no reason to hand a browser 1024px
    of somebody's face."""
    [job] = _upload(client, user, one_image()).json()["created"]

    res = client.get(
        f"/api/uploads/{job['id']}/image",
        params={"size": "orig"},
        headers=user["headers"],
    )

    assert res.status_code == 422


# ----------------------------------------------------------------- matching


def test_matching_an_empty_corpus_fails_loudly(auth_client):
    """Better a 503 that names the fix than a match against nothing."""
    res = auth_client.post("/api/match", json={"image": _b64()})

    assert res.status_code == 503
    assert "ingest_dogs" in res.json()["detail"]


def test_match_needs_an_actual_image(auth_client):
    assert auth_client.post("/api/match", json={}).status_code == 422
    assert auth_client.post("/api/match", json={"image": "not base64!!"}).status_code == 422


def test_match_accepts_a_data_url(auth_client, matcher):
    """Browsers hand out `data:image/png;base64,...` from a canvas or a file
    reader, so accepting the prefix saves every caller stripping it."""
    res = auth_client.post("/api/match", json={"image": "data:image/jpeg;base64," + _b64()})

    assert res.status_code == 201


def test_a_match_names_a_real_dog(auth_client, matcher, dog_corpus):
    res = auth_client.post("/api/match", json={"image": _b64()})

    assert res.status_code == 201
    body = res.json()
    assert body["dog"]["slug"] in dog_corpus
    assert body["dogIndex"] is not None
    assert 0 <= body["score"] <= 1
    # Shared traits are only reported where the person and the dog are *both*
    # above average, so an unremarkable pair legitimately shares none.
    assert len(body["sharedTraits"]) <= 3
    assert "breedName" not in body, "AFHQ has no breed labels — we stopped claiming them"


def test_the_same_photo_always_matches_the_same_dog(auth_client, matcher, dog_corpus):
    """Stability matters for demos: a page refresh must not reroll the answer."""
    payload = _b64(colour=(90, 30, 200))
    first = auth_client.post("/api/match", json={"image": payload}).json()
    second = auth_client.post("/api/match", json={"image": payload}).json()

    assert first["dog"]["slug"] == second["dog"]["slug"]
    assert first["sharedTraits"] == second["sharedTraits"]


def test_a_queued_upload_ends_up_matched_to_a_dog(client, user, matcher, dog_corpus):
    """The whole path: multipart in, worker picks it up, dog comes out."""
    [job] = _upload(client, user, one_image()).json()["created"]

    deadline = time.time() + 15
    finished = None
    while time.time() < deadline:
        rows = client.get("/api/uploads", headers=user["headers"]).json()
        finished = next((r for r in rows if r["id"] == job["id"]), None)
        if finished and finished["status"] in {"done", "error"}:
            break
        time.sleep(0.2)

    assert finished is not None and finished["status"] == "done", finished
    assert finished["dog"]["slug"] in dog_corpus
    assert finished["dog"]["imageUrl"].startswith("/dogs/256/")


# --------------------------------------------------------- queue fairness
#
# `_select_next` is pure-function-tested directly, on plain unpersisted rows
# — no client, no DB, no worker pool, because the interesting logic is the
# scheduling arithmetic (Weighted Start-time Fair Queueing — see queue.py's
# module docstring), not that the real upload/claim plumbing works, which
# test_a_queued_upload_ends_up_matched_to_a_dog above already covers.


def _job(id, owner_id, *, urgent=False, byte_size=1_000, created_at=None):
    """An unpersisted UploadJob, just real enough for `_select_next`."""
    from app.models import UploadJob

    return UploadJob(
        id=id,
        owner_id=owner_id,
        original_filename="x.jpg",
        content_type="image/jpeg",
        urgent=urgent,
        byte_size=byte_size,
        created_at=created_at or datetime.utcnow(),
    )


def test_a_bulk_owner_cannot_starve_a_single_owner():
    """The guidelines' explicit fear, verbatim: 'client A doesn't get his
    single image not processed for a long time because client B sent 100
    images.'"""
    from app.uploads import queue

    queue._reset_fairness_state()
    remaining = [_job(i, owner_id=1) for i in range(100)] + [_job(999, owner_id=2)]

    claimed_owners = []
    while remaining:
        job = queue._select_next(remaining)
        claimed_owners.append(job.owner_id)
        remaining.remove(job)
        if job.owner_id == 2:
            break

    # Owner 2's one job is claimed within the first round, nowhere near the
    # back of owner 1's 100-deep backlog.
    assert claimed_owners.index(2) <= 1, claimed_owners[:5]


def test_a_long_idle_owner_does_not_steal_the_queue():
    """An owner who was served once long ago, then went idle while another
    owner stayed continuously backlogged (and so is legitimately behind now),
    must not resume with their ancient low clock and cut in front of them —
    the fix from the SFQ paper (Goyal, Vin & Cheng, 1996)."""
    from app.uploads import queue

    queue._reset_fairness_state()
    queue._vt[1] = 10.0  # owner 1's clock, from ages ago
    queue._vt[2] = 480.0  # owner 2, continuously backlogged, a bit behind
    queue._global_vt = 500.0  # ...the world has moved on since owner 1's turn
    queue._backlogged.add(2)  # owner 2 never left the queue; owner 1 did

    remaining = [_job(1, owner_id=1), _job(2, owner_id=2)]  # owner 1 returns
    picked = queue._select_next(remaining)

    assert picked.owner_id == 2, "the stale clock must not let owner 1 cut ahead of someone already waiting"


def test_urgent_gets_a_bounded_head_start_not_an_absolute_one():
    """Urgent should win against a roughly-tied competitor, but a genuinely
    far-behind owner still wins regardless — the discount is capped, so
    marking everything urgent can never starve anyone."""
    from app.uploads import queue

    queue._reset_fairness_state()
    tied = [_job(1, owner_id=10, urgent=True), _job(2, owner_id=20, urgent=False)]
    assert queue._select_next(tied).owner_id == 10, "urgent should win a tied race"

    queue._reset_fairness_state()
    queue._vt[10] = 100.0  # urgent owner, but just served — caught up
    queue._vt[20] = 0.0  # ordinary owner, continuously backlogged, way behind
    queue._global_vt = 100.0
    queue._backlogged.add(20)  # owner 20 never left the queue; owner 10 is arriving now
    far_behind = [_job(1, owner_id=10, urgent=True), _job(2, owner_id=20, urgent=False)]
    assert queue._select_next(far_behind).owner_id == 20, (
        "a bounded discount must not be enough to cut in front of an owner this far behind"
    )


def test_aging_lets_an_old_large_photo_win_eventually():
    """Without aging, an owner who keeps adding new small photos could leave
    an old large photo of their own stuck behind an endless stream of newer,
    cheaper siblings forever. Aging shrinks a job's effective cost the longer
    it waits, until even a large photo wins."""
    from datetime import timedelta

    from app.uploads import queue

    queue._reset_fairness_state()
    old_big = _job(1, owner_id=1, byte_size=5_000_000, created_at=datetime.utcnow() - timedelta(seconds=120))
    fresh_small = _job(2, owner_id=1, byte_size=1_000)

    picked = queue._select_next([old_big, fresh_small])

    assert picked.id == old_big.id, "a photo that has waited 2 minutes should now beat a brand-new small one"


async def test_the_queue_is_fair_and_scalable_with_fifty_images(client, user_factory, monkeypatch):
    """The guidelines' explicit ask, run for real: at least 50 images, more
    than one client, a mocked model with an artificial delay — checking the
    queue is both fair (nobody starves) and scalable (concurrency actually
    helps).

    `match_dog` is patched rather than using the `matcher`/`dog_corpus`
    fixtures: this test is about the queue's scheduling, not the model's
    arithmetic (test_ml.py's job), and the guidelines explicitly suggest a
    mock model with a delay to keep a 50-image test cheap to run.
    """
    from app.uploads import queue

    # Deliberately larger than real per-job work: real overhead (image
    # decode/resize/encode at upload time, two SQLite commits per job) is
    # only a few tens of ms and would otherwise swamp a tiny artificial
    # delay, making a "did concurrency help" comparison noise-dominated
    # rather than a real signal.
    FAKE_DELAY = 0.3

    def fake_match_dog(db, path):
        time.sleep(FAKE_DELAY)  # the "artificial delay" the guidelines ask for
        return queue.DogMatchResult(
            dog_asset_id=1, manifest_index=None, slug="stub", score=0.5, shared_traits=[]
        )

    monkeypatch.setattr(queue, "match_dog", fake_match_dog)
    monkeypatch.setattr(queue, "MIN_PROCESS_SECONDS", 0.0)
    monkeypatch.setattr(queue, "MAX_PROCESS_SECONDS", 0.0)
    monkeypatch.setattr(queue, "IDLE_POLL_SECONDS", 0.02)

    bulk = user_factory()
    lonely = user_factory()

    t0 = time.monotonic()
    bulk_ids: list[int] = []
    for start in range(0, 49, 20):  # MAX_FILES_PER_REQUEST caps a batch at 20
        chunk = [
            ("files", (f"{i}.jpg", make_image(64, 64), "image/jpeg"))
            for i in range(start, min(start + 20, 49))
        ]
        res = _upload(client, bulk, chunk)
        bulk_ids.extend(j["id"] for j in res.json()["created"])
    lonely_id = _upload(client, lonely, one_image("only.jpg")).json()["created"][0]["id"]
    assert len(bulk_ids) + 1 == 50, "at least 50 images overall, per the guidelines"

    # Fairness: the lone client's single photo must not wait behind the bulk
    # client's whole 49-photo batch just because it arrived alongside them —
    # nowhere near the ~15s a batch that deep would cost if processed serially.
    deadline = time.time() + 20
    lonely_row = None
    while time.time() < deadline:
        lonely_row = client.get(f"/api/uploads/{lonely_id}", headers=lonely["headers"]).json()
        if lonely_row["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    lonely_wait = time.monotonic() - t0
    assert lonely_row is not None and lonely_row["status"] == "done", lonely_row
    assert lonely_wait < 5.0, f"the lone client waited {lonely_wait:.2f}s behind a 49-photo batch"

    # Scalability: once all 50 are done, total wall time should reflect real
    # concurrency. The bound is deliberately generous (not tuned tight to one
    # machine's overhead) so it holds however many cores WORKER_COUNT ended up
    # using — it only fails if parallelism provided essentially no benefit.
    deadline = time.time() + 30
    rows: list[dict] = []
    while time.time() < deadline:
        rows = client.get("/api/uploads", headers=bulk["headers"]).json()
        if all(r["status"] in ("done", "error") for r in rows):
            break
        time.sleep(0.02)
    assert all(r["status"] == "done" for r in rows), rows
    total = time.monotonic() - t0
    serial_estimate = 50 * FAKE_DELAY
    if queue.WORKER_COUNT > 1:
        assert total < serial_estimate * 0.85, (
            f"50 jobs took {total:.2f}s across {queue.WORKER_COUNT} workers — "
            f"barely faster than doing them one at a time ({serial_estimate:.2f}s)"
        )


def test_a_job_whose_photo_vanished_errors_instead_of_inventing_a_match(dog_corpus, tmp_path):
    """The crash-between-commit-and-write case.

    A job row is committed before its derivatives are written, so a process
    killed in that window leaves a queued job with no files. Falling back to a
    constant seed would mark it `done` with a real dog — and give every job in
    that state the *same* dog.
    """
    from app.database import SessionLocal
    from app.model import SourceImageMissing, match_dog

    db = SessionLocal()
    try:
        with pytest.raises(SourceImageMissing):
            match_dog(db, tmp_path / "never-written.jpg")
    finally:
        db.close()


@pytest.mark.parametrize("with_dog", [True, False], ids=["matched", "still processing"])
def test_a_job_can_still_be_rendered_after_it_leaves_its_session(dog_corpus, with_dog):
    """What the worker sends over the WebSocket, tested where it can't hang.

    The workers build their `upload_update` events from a job they have already
    detached from its session (queue.py `_detach`). If the `dog` relationship
    isn't loaded first, `as_dict()` raises DetachedInstanceError — and
    `_notify` catches that and logs at debug, so the client silently never
    hears its match is ready while `GET /api/uploads` keeps working fine.

    Asserted at this level rather than over a real socket on purpose: when the
    bug is present *no* event is emitted at all, so a socket test blocks on
    receive() forever instead of failing. This raises immediately.

    The `with_dog=False` case is not redundant — a detached instance refuses
    the lazy load rather than short-circuiting on the NULL foreign key, so the
    in-progress event breaks too.
    """
    from app.database import SessionLocal
    from app.models import DogAsset, UploadJob
    from app.uploads.queue import _detach, _event

    db = SessionLocal()
    try:
        dog = db.query(DogAsset).order_by(DogAsset.slug).first()
        job = UploadJob(
            owner_id="own_detach",
            original_filename="me.jpg",
            content_type="image/jpeg",
            status="done" if with_dog else "processing",
            dog_asset_id=dog.id if with_dog else None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        detached = _detach(db, job)
    finally:
        db.close()  # the session is gone; the worker notifies after this point

    payload = _event(detached)["payload"]  # raises DetachedInstanceError if unloaded

    assert payload["status"] == ("done" if with_dog else "processing")
    if with_dog:
        assert payload["dog"]["slug"] == dog.slug
        assert payload["dog"]["imageUrl"].startswith("/dogs/256/")
    else:
        assert payload["dog"] is None


# --------------------------------------------------------------- corpus API


def test_corpus_stats_report_an_empty_corpus(client):
    stats = client.get("/api/dogs/stats").json()

    assert stats == {"total": 0, "embedded": 0, "embeddingModel": None}


def test_corpus_stats_count_what_was_ingested(client, dog_corpus):
    stats = client.get("/api/dogs/stats").json()

    assert stats["total"] == len(dog_corpus)
    assert stats["embedded"] == 0, "nothing is embedded until the next phase"


def test_a_dog_can_be_looked_up_by_its_wire_index(client, dog_corpus):
    dog = client.get("/api/dogs/0").json()

    assert dog["slug"] == sorted(dog_corpus)[0]
    assert dog["thumbUrl"] == f"/dogs/128/{dog['slug']}.webp"
    assert dog["fullUrl"] == f"/dogs/512/{dog['slug']}.jpg"


def test_an_out_of_range_dog_index_is_a_404(client, dog_corpus):
    assert client.get("/api/dogs/99999").status_code == 404


def test_the_manifest_endpoint_matches_the_ingest_ordering(client, dog_corpus):
    body = client.get("/api/dogs/manifest").json()

    assert body["slugs"] == sorted(dog_corpus)
    assert body["count"] == len(dog_corpus)


def test_one_upload_can_be_fetched_by_id(client, user, dog_corpus):
    """What the result page calls."""
    files = [("files", ("me.png", make_image(240, 240), "image/png"))]
    created = _upload(client, user, files, urgent="[false]").json()["created"][0]

    fetched = client.get(f"/api/uploads/{created['id']}", headers=user["headers"])

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_someone_elses_upload_is_a_404_not_a_403(client, user, other_user, dog_corpus):
    """A 403 would confirm the id exists, which is enough to enumerate uploads."""
    files = [("files", ("me.png", make_image(240, 240), "image/png"))]
    created = _upload(client, user, files, urgent="[false]").json()["created"][0]

    assert (
        client.get(f"/api/uploads/{created['id']}", headers=other_user["headers"]).status_code
        == 404
    )
    assert client.get("/api/uploads/999999", headers=user["headers"]).status_code == 404
    assert client.get(f"/api/uploads/{created['id']}").status_code == 401, (
        "anonymous is a 401, not a 404 — there is no identity to compare yet"
    )
