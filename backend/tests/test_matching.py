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

import pytest
from conftest import make_image

from app.storage import layout


def _upload(client, owner: str, files, urgent="[]"):
    return client.post(
        "/api/uploads",
        data={"ownerId": owner, "urgent": urgent},
        files=files,
    )


def one_image(name="me.jpg", **kwargs):
    return [("files", (name, make_image(**kwargs), "image/jpeg"))]


def _b64(**kwargs) -> str:
    """A real encoded image, base64'd — what POST /api/match now expects."""
    return base64.b64encode(make_image(**kwargs)).decode()


# ------------------------------------------------------------------ storing


def test_an_uploaded_photo_is_stored_re_encoded_with_its_facts_recorded(client):
    res = _upload(client, "own_store", one_image(width=800, height=600))

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


def test_a_sideways_photo_is_stored_upright(client):
    """EXIF orientation is applied at ingest, so nothing downstream — the
    model included — has to know the tag exists."""
    res = _upload(client, "own_exif", one_image(width=800, height=600, exif=True))

    [job] = res.json()["created"]
    assert (job["width"], job["height"]) == (600, 800)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(b"MZ\x90\x00" + b"\x00" * 500, "only PNG and JPG", id="a renamed executable"),
        pytest.param(b"\xff\xd8\xff" + b"\x00" * 500, "readable image", id="jpeg magic, junk body"),
    ],
)
def test_a_file_that_isnt_really_an_image_is_rejected(client, payload, expected):
    res = _upload(client, "own_junk", [("files", ("evil.jpg", payload, "image/jpeg"))])

    assert res.status_code == 201, "a bad file in the batch doesn't fail the request"
    body = res.json()
    assert body["created"] == []
    assert expected in body["rejected"][0]["reason"]


def test_a_rejected_file_leaves_no_job_behind(client):
    """The second magic-bytes case gets past the sniff and dies at decode —
    the path where a row could plausibly be orphaned."""
    _upload(client, "own_orphan", [("files", ("evil.jpg", b"\xff\xd8\xff" + b"\x00" * 500, "image/jpeg"))])

    assert client.get("/api/uploads", params={"ownerId": "own_orphan"}).json() == []


def test_a_batch_bigger_than_the_cap_is_refused(client):
    files = [("files", (f"{i}.jpg", make_image(64, 64), "image/jpeg")) for i in range(25)]

    res = _upload(client, "own_flood", files)

    assert res.status_code == 422
    assert "at most" in res.json()["detail"]


def test_a_good_file_still_lands_when_a_sibling_is_junk(client):
    files = [
        ("files", ("good.jpg", make_image(200, 200), "image/jpeg")),
        ("files", ("bad.jpg", b"nope", "image/jpeg")),
    ]

    body = _upload(client, "own_mixed", files).json()

    assert len(body["created"]) == 1 and len(body["rejected"]) == 1


# ------------------------------------------------------------------ serving


def test_a_photo_is_only_served_to_its_owner(client):
    [job] = _upload(client, "own_a", one_image()).json()["created"]

    mine = client.get(f"/api/uploads/{job['id']}/image", params={"ownerId": "own_a"})
    theirs = client.get(f"/api/uploads/{job['id']}/image", params={"ownerId": "own_b"})

    assert mine.status_code == 200
    assert theirs.status_code == 404, "someone else's photo must not be reachable"


def test_uploaded_photos_are_never_cached(client):
    """Personal data, unlike the dog corpus, must not sit in a shared cache."""
    [job] = _upload(client, "own_cache", one_image()).json()["created"]

    res = client.get(f"/api/uploads/{job['id']}/image", params={"ownerId": "own_cache"})

    assert res.headers["cache-control"] == "private, no-store"


def test_the_full_resolution_original_is_not_servable(client):
    """`orig` is the model's input; there's no reason to hand a browser 1024px
    of somebody's face."""
    [job] = _upload(client, "own_orig", one_image()).json()["created"]

    res = client.get(
        f"/api/uploads/{job['id']}/image", params={"ownerId": "own_orig", "size": "orig"}
    )

    assert res.status_code == 422


# ----------------------------------------------------------------- matching


def test_matching_an_empty_corpus_fails_loudly(client):
    """Better a 503 that names the fix than a match against nothing."""
    res = client.post("/api/match", json={"image": _b64()})

    assert res.status_code == 503
    assert "ingest_dogs" in res.json()["detail"]


def test_match_needs_an_actual_image(client):
    assert client.post("/api/match", json={}).status_code == 422
    assert client.post("/api/match", json={"image": "not base64!!"}).status_code == 422


def test_match_accepts_a_data_url(client, matcher):
    """Browsers hand out `data:image/png;base64,...` from a canvas or a file
    reader, so accepting the prefix saves every caller stripping it."""
    res = client.post("/api/match", json={"image": "data:image/jpeg;base64," + _b64()})

    assert res.status_code == 201


def test_a_match_names_a_real_dog(client, matcher, dog_corpus):
    res = client.post("/api/match", json={"image": _b64()})

    assert res.status_code == 201
    body = res.json()
    assert body["dog"]["slug"] in dog_corpus
    assert body["dogIndex"] is not None
    assert 0 <= body["score"] <= 1
    # Shared traits are only reported where the person and the dog are *both*
    # above average, so an unremarkable pair legitimately shares none.
    assert len(body["sharedTraits"]) <= 3
    assert "breedName" not in body, "AFHQ has no breed labels — we stopped claiming them"


def test_the_same_photo_always_matches_the_same_dog(client, matcher, dog_corpus):
    """Stability matters for demos: a page refresh must not reroll the answer."""
    payload = _b64(colour=(90, 30, 200))
    first = client.post("/api/match", json={"image": payload}).json()
    second = client.post("/api/match", json={"image": payload}).json()

    assert first["dog"]["slug"] == second["dog"]["slug"]
    assert first["sharedTraits"] == second["sharedTraits"]


def test_a_queued_upload_ends_up_matched_to_a_dog(client, matcher, dog_corpus):
    """The whole path: multipart in, worker picks it up, dog comes out."""
    [job] = _upload(client, "own_e2e", one_image()).json()["created"]

    deadline = time.time() + 15
    finished = None
    while time.time() < deadline:
        rows = client.get("/api/uploads", params={"ownerId": "own_e2e"}).json()
        finished = next((r for r in rows if r["id"] == job["id"]), None)
        if finished and finished["status"] in {"done", "error"}:
            break
        time.sleep(0.2)

    assert finished is not None and finished["status"] == "done", finished
    assert finished["dog"]["slug"] in dog_corpus
    assert finished["dog"]["imageUrl"].startswith("/dogs/256/")


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


def test_one_upload_can_be_fetched_by_id(client, dog_corpus):
    """What the result page calls."""
    files = [("files", ("me.png", make_image(240, 240), "image/png"))]
    created = client.post(
        "/api/uploads", data={"ownerId": "solo", "urgent": "[false]"}, files=files
    ).json()["created"][0]

    fetched = client.get(f"/api/uploads/{created['id']}?ownerId=solo")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_someone_elses_upload_is_a_404_not_a_403(client, dog_corpus):
    """A 403 would confirm the id exists, which is enough to enumerate uploads."""
    files = [("files", ("me.png", make_image(240, 240), "image/png"))]
    created = client.post(
        "/api/uploads", data={"ownerId": "owner", "urgent": "[false]"}, files=files
    ).json()["created"][0]

    assert client.get(f"/api/uploads/{created['id']}?ownerId=someone-else").status_code == 404
    assert client.get("/api/uploads/999999?ownerId=owner").status_code == 404
