"""The storage layer: sanitising images, the paths they land on, and ingest.

These cover the promises DATA_STORAGE.md makes — that nothing a client sent is
stored verbatim, that a hostile file fails with a message instead of a
traceback, and that running the ingest twice is a no-op.
"""
import sys
from pathlib import Path

import ingest_dogs
import pytest
from conftest import make_image
from PIL import Image

from app.storage import layout
from app.storage.imaging import ImageRejected, checksum_of, decode, write_derivatives


# ------------------------------------------------------------------ decode


def test_exif_orientation_is_applied_then_discarded():
    """A portrait phone photo comes out upright with no tag left behind.

    Both halves matter: applying the tag is why photos aren't sideways, and
    dropping it is why re-encoding strips GPS along with everything else.
    """
    image = decode(make_image(600, 400, exif=True))

    assert image.size == (400, 600), "orientation=6 should have rotated it"
    assert not image.getexif(), "the EXIF block should be gone, not just ignored"


def test_transparency_is_flattened_to_rgb():
    image = decode(make_image(120, 120, fmt="PNG", mode="RGBA"))

    assert image.mode == "RGB"


@pytest.mark.parametrize(
    ("data", "because"),
    [
        pytest.param(b"", "empty", id="no bytes at all"),
        pytest.param(b"MZ\x90\x00" + b"\x00" * 200, "an exe", id="a renamed executable"),
        pytest.param(make_image()[:80], "truncated", id="a half-uploaded file"),
    ],
)
def test_junk_is_rejected_with_a_message(data, because):
    with pytest.raises(ImageRejected) as caught:
        decode(data)

    assert str(caught.value), f"{because} should come back with something to show the user"


def test_a_decompression_bomb_is_refused(monkeypatch):
    """A 4-pixel image claiming to be enormous must not be decoded.

    Patching the ceiling rather than building a real bomb: the point is that
    the guard fires, and generating 50 megapixels to prove it would make the
    suite slow for no extra confidence.
    """
    monkeypatch.setattr("app.storage.imaging.MAX_PIXELS", 3)

    with pytest.raises(ImageRejected):
        decode(make_image(2, 2))


# ------------------------------------------------------------- derivatives


def test_derivatives_are_downscaled_but_never_upscaled(tmp_path):
    small = tmp_path / "small.webp"
    large = tmp_path / "large.jpg"
    data = make_image(300, 200)

    stored = write_derivatives(data, {large: (512, ".jpg"), small: (128, ".webp")})

    with Image.open(large) as archived:
        assert archived.size == (300, 200), "a 300px source must not be blown up to 512"
    with Image.open(small) as thumb:
        assert thumb.size == (128, 85), "the thumbnail keeps the 3:2 aspect ratio"

    # The reported facts describe the largest derivative — the copy the model
    # reads — not the last one written.
    assert (stored.width, stored.height) == (300, 200)
    assert stored.checksum == checksum_of(data), "the checksum is of the source bytes"


def test_a_stored_file_carries_no_metadata_forward(tmp_path):
    out = tmp_path / "clean.jpg"

    write_derivatives(make_image(400, 300, exif=True), {out: (512, ".jpg")})

    with Image.open(out) as written:
        assert not written.getexif()
        assert "icc_profile" not in written.info


# ------------------------------------------------------------------ layout


def test_upload_paths_shard_so_one_directory_never_grows_unbounded():
    assert layout.upload_path(17, "orig").parent.name == "0000"
    assert layout.upload_path(4001, "orig").parent.name == "0004"


def test_deleting_an_upload_removes_every_derivative(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DATA_DIR", str(tmp_path))
    layout.ensure_upload_dirs(7)
    write_derivatives(
        make_image(300, 300),
        {layout.upload_path(7, size): spec for size, spec in layout.UPLOAD_SIZES.items()},
    )
    assert all(layout.upload_path(7, s).exists() for s in layout.UPLOAD_SIZES)

    removed = layout.delete_upload_files(7)

    assert removed == len(layout.UPLOAD_SIZES)
    assert not any(layout.upload_path(7, s).exists() for s in layout.UPLOAD_SIZES)


@pytest.mark.parametrize("size", ["1024", "orig", ""])
def test_an_unknown_dog_size_is_a_programming_error(size):
    with pytest.raises(ValueError):
        layout.dog_path("flickr_dog_000001", size)


# ------------------------------------------------------------------ ingest


def test_ingest_writes_every_derivative_and_a_row_each(dog_corpus):
    from app.database import SessionLocal
    from app.models import DogAsset

    db = SessionLocal()
    try:
        dogs = db.query(DogAsset).order_by(DogAsset.slug).all()
        assert [d.slug for d in dogs] == dog_corpus
        assert len(dogs) == 5

        for dog in dogs:
            for size in layout.DOG_SIZES:
                assert layout.dog_path(dog.slug, size).exists(), f"{dog.slug} missing {size}"
            assert dog.checksum and dog.byte_size > 0
            assert dog.embedding is None, "embeddings are the next phase, not this one"
    finally:
        db.close()


def test_manifest_indices_are_dense_and_follow_slug_order(dog_corpus):
    from app.database import SessionLocal
    from app.models import DogAsset

    db = SessionLocal()
    try:
        rows = db.query(DogAsset).order_by(DogAsset.manifest_index).all()
        assert [r.manifest_index for r in rows] == list(range(len(dog_corpus)))
        # Ordering must depend only on which dogs exist, never on insertion
        # order — the frontend resolves an index through a sorted list.
        assert [r.slug for r in rows] == sorted(dog_corpus)
    finally:
        db.close()


def test_running_ingest_again_changes_nothing(dog_corpus, tmp_path):
    """Idempotency is what makes an interrupted 5,239-image run resumable."""
    import ingest_dogs

    source = tmp_path / "again"
    source.mkdir()
    for i in range(5):
        (source / f"flickr_dog_{i:06d}.jpg").write_bytes(
            make_image(320, 320, colour=(40 * i + 10, 90, 140))
        )

    ingested, skipped, errors = ingest_dogs.ingest(source, limit=None, workers=1)

    assert (ingested, skipped, errors) == (0, 5, [])


def test_ingest_redoes_a_dog_whose_files_were_lost(dog_corpus, tmp_path):
    """A row without its pixels is worse than no row: the site 404s the image.

    So the skip test is 'row AND files', not 'row'.
    """
    import ingest_dogs

    layout.dog_path(dog_corpus[0], "256").unlink()

    source = tmp_path / "recover"
    source.mkdir()
    (source / f"{dog_corpus[0]}.jpg").write_bytes(make_image(320, 320, colour=(10, 90, 140)))

    ingested, skipped, _ = ingest_dogs.ingest(source, limit=None, workers=1)

    assert (ingested, skipped) == (1, 0)
    assert layout.dog_path(dog_corpus[0], "256").exists()


def test_two_identical_photos_under_different_names_both_ingest(tmp_path):
    """AFHQ ships byte-identical photos under different filenames.

    A unique constraint on the checksum turned that into an IntegrityError that
    aborted the whole run at whichever image happened to hit it — so identity
    is the slug, and the checksum only reports the duplication.
    """
    import ingest_dogs
    from app.database import SessionLocal

    source = tmp_path / "twins"
    (source / "train").mkdir(parents=True)
    (source / "val").mkdir(parents=True)
    same = make_image(256, 256, colour=(7, 7, 7))
    (source / "train" / "flickr_dog_000000.jpg").write_bytes(same)
    (source / "val" / "flickr_dog_000100.jpg").write_bytes(same)

    ingested, _, errors = ingest_dogs.ingest(source, limit=None, workers=1)

    assert (ingested, errors) == (2, [])
    db = SessionLocal()
    try:
        duplicates = ingest_dogs.report_duplicates(db)
        assert [count for _, count in duplicates] == [2], "the duplication should be reported"
    finally:
        db.close()


def test_a_corrupt_source_file_is_reported_not_fatal(tmp_path):
    """One bad file in 5,239 must not abort the run."""
    import ingest_dogs

    source = tmp_path / "mixed"
    source.mkdir()
    (source / "good_dog.jpg").write_bytes(make_image(200, 200))
    (source / "bad_dog.jpg").write_bytes(b"not an image, just vibes")

    ingested, _, errors = ingest_dogs.ingest(source, limit=None, workers=1)

    assert ingested == 1
    assert len(errors) == 1 and "bad_dog" in errors[0]


def test_duplicate_slugs_are_refused_before_any_work_happens(tmp_path):
    """Two files with the same stem would fight over one output filename."""
    import ingest_dogs

    source = tmp_path / "clash"
    (source / "train").mkdir(parents=True)
    (source / "val").mkdir(parents=True)
    (source / "train" / "dog_1.jpg").write_bytes(make_image(100, 100))
    (source / "val" / "dog_1.jpg").write_bytes(make_image(100, 100))

    with pytest.raises(SystemExit, match="share the name"):
        ingest_dogs.discover(source)


def test_discover_reads_the_split_out_of_the_afhq_layout(tmp_path):
    import ingest_dogs

    source = tmp_path / "afhq"
    (source / "train" / "dog").mkdir(parents=True)
    (source / "val" / "dog").mkdir(parents=True)
    (source / "train" / "dog" / "a.jpg").write_bytes(make_image(64, 64))
    (source / "val" / "dog" / "b.jpg").write_bytes(make_image(64, 64))

    splits = {slug: split for _, slug, split in ingest_dogs.discover(source)}

    assert splits == {"a": "train", "b": "val"}


def test_discover_skips_the_cats_and_the_wild_animals(tmp_path):
    """AFHQ ships three classes side by side, so pointing --source at the
    extracted archive must not ingest 16,130 animals instead of 5,239 dogs."""
    source = tmp_path / "afhq"
    for animal in ("dog", "cat", "wild"):
        (source / "train" / animal).mkdir(parents=True)
        (source / "train" / animal / f"{animal}_1.jpg").write_bytes(make_image(64, 64))

    slugs = {slug for _, slug, _ in ingest_dogs.discover(source)}

    assert slugs == {"dog_1"}


def test_a_manifest_that_disagrees_with_the_database_is_fatal(tmp_path):
    """Silently serving 5,239 wrong dogs is the failure this prevents."""
    import ingest_dogs

    manifest = tmp_path / "dogImages.json"
    manifest.write_text('["flickr_dog_000000"]')

    with pytest.raises(SystemExit, match="MANIFEST MISMATCH"):
        ingest_dogs.check_manifest(["flickr_dog_000000", "flickr_dog_000001"], manifest, write=False)


def test_the_manifest_can_be_regenerated(tmp_path):
    import ingest_dogs

    manifest = tmp_path / "dogImages.json"

    ingest_dogs.check_manifest(["a", "b"], manifest, write=True)

    assert manifest.read_text().startswith("[")
    ingest_dogs.check_manifest(["a", "b"], manifest, write=False)  # now verifies clean


# --------------------------------------------------------------- migration


OLD_UPLOAD_JOBS = """
CREATE TABLE upload_jobs (
 id INTEGER PRIMARY KEY, owner_id VARCHAR(64) NOT NULL,
 original_filename VARCHAR(255) NOT NULL, content_type VARCHAR(30) NOT NULL,
 urgent BOOLEAN, status VARCHAR(20) NOT NULL,
 breed_name VARCHAR(120), trait VARCHAR(200), confidence FLOAT,
 error VARCHAR(300), created_at DATETIME, finished_at DATETIME)
"""

OLD_MATCHES = """
CREATE TABLE matches (
 id INTEGER PRIMARY KEY, user_id INTEGER,
 breed_name VARCHAR(120) NOT NULL, trait VARCHAR(200), confidence FLOAT,
 created_at DATETIME)
"""


def test_migrating_an_old_database_adds_and_drops_the_right_columns(tmp_path):
    """The deploy case: `dbdata` is a named volume, so the VM keeps the old
    tables. create_all() adds tables but never columns, so without a migration
    every upload/forum/match query dies on a missing column at once.

    Driven through `plan()` against a throwaway engine rather than `migrate()`:
    migrate() binds to the process-wide engine, and rebinding that mid-suite
    would leave every later test talking to the wrong database.
    """
    import sqlalchemy
    from sqlalchemy import inspect, text

    import migrate_schema

    db_file = tmp_path / "old.db"
    old_engine = sqlalchemy.create_engine(f"sqlite:///{db_file}")
    with old_engine.begin() as conn:
        # The pre-change shape of the two tables that changed.
        conn.execute(text(OLD_UPLOAD_JOBS))
        conn.execute(text(OLD_MATCHES))
        conn.execute(
            text(
                "INSERT INTO upload_jobs (owner_id, original_filename, content_type,"
                " status, breed_name) VALUES ('o', 'me.jpg', 'image/jpeg', 'done', 'Pug')"
            )
        )

    with old_engine.begin() as conn:
        statements = migrate_schema.plan(conn)
        assert any("ADD COLUMN dog_asset_id" in s for s in statements)
        assert any("upload_jobs ADD COLUMN checksum" in s for s in statements)
        assert any("DROP COLUMN breed_name" in s for s in statements)
        for statement in statements:
            conn.execute(text(statement))

    with old_engine.begin() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("upload_jobs")}
        assert {"checksum", "byte_size", "width", "height", "dog_asset_id", "score"} <= columns
        assert not {"breed_name", "trait", "confidence"} & columns
        assert (
            conn.execute(text("SELECT original_filename FROM upload_jobs")).scalar() == "me.jpg"
        ), "existing rows survive the migration"

        # matches.breed_name was NOT NULL, so if the drop hadn't happened this
        # INSERT would fail — the new code never supplies a breed.
        conn.execute(
            text("INSERT INTO matches (user_id, dog_asset_id, score) VALUES (NULL, NULL, 0.5)")
        )

        assert migrate_schema.plan(conn) == [], "a second run must be a no-op"

    old_engine.dispose()


def test_migrating_a_fresh_database_is_a_no_op(tmp_path):
    """Running it on a VM that has never seen the old schema must do nothing."""
    import sqlalchemy

    import migrate_schema

    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    try:
        with engine.begin() as conn:
            assert migrate_schema.plan(conn) == []
    finally:
        engine.dispose()


def test_the_committed_manifest_is_a_list_of_slugs():
    """dogSrc.ts appends the extension, so an entry carrying one would give
    `/dogs/256/flickr_dog_000002.jpg.webp`."""
    import json

    manifest = Path(__file__).resolve().parents[2] / "src" / "lib" / "dogImages.json"
    slugs = json.loads(manifest.read_text())

    assert len(slugs) == 5239
    assert not any("." in slug for slug in slugs)
    assert slugs == sorted(slugs), "the ingest deals indices in sorted order"
