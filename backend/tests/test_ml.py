"""The matching model: preprocessing, face cropping, and the retrieval itself.

These run against a 6KB stand-in encoder, not CLIP. That is deliberate: the
350MB export is gitignored and CI could not use it anyway, and what is worth
testing here is *our* arithmetic — the centring, the z-scoring, the blend, how
a shared trait is chosen — not OpenAI's weights. A test that only passes
because CLIP is good tells you nothing when it breaks.
"""
import numpy as np
import pytest
from conftest import PassThroughCropper, make_image
from PIL import Image

from app.ml import attributes as attrs
from app.ml import matcher as ml_matcher
from app.ml.encoder import EMBEDDING_DIM
from app.ml.faces import DEFAULT_MARGIN, FaceCropper, NoFaceFound
from app.ml.preprocess import CLIP_MEAN, SIDE, preprocess
from app.ml.vectors import l2_normalize, pack, unpack


# ----------------------------------------------------------- preprocessing


@pytest.mark.parametrize(
    ("width", "height"),
    [(640, 480), (480, 640), (224, 224), (100, 3000)],
    ids=["landscape", "portrait", "exact", "extreme"],
)
def test_preprocessing_always_produces_the_shape_the_encoder_wants(width, height):
    batch = preprocess(Image.new("RGB", (width, height), (120, 90, 40)))

    assert batch.shape == (1, 3, SIDE, SIDE)
    assert batch.dtype == np.float32


def test_preprocessing_centres_on_clips_own_statistics():
    """A mid-grey image should land near the normalised origin, because the
    channel means being subtracted are CLIP's own."""
    grey = Image.new("RGB", (300, 300), tuple((CLIP_MEAN * 255).astype(int)))

    batch = preprocess(grey)

    assert np.abs(batch).max() < 0.05


def test_preprocessing_takes_the_middle_of_a_wide_image():
    """A crop from the corner would frame a different part of every photo, and
    the dog corpus is centred, so the human input has to be too."""
    wide = Image.new("RGB", (900, 300), (255, 0, 0))
    wide.paste(Image.new("RGB", (300, 300), (0, 0, 255)), (300, 0))

    batch = preprocess(wide)

    # Blue channel dominates only if the middle third is what survived.
    assert batch[0, 2].mean() > batch[0, 0].mean()


# ------------------------------------------------------------------- faces


def test_a_photo_with_no_face_is_refused():
    """The guidelines' 'robust to a picture meant to make the model not output
    a dog' requirement — a sandwich must not confidently return a dog."""
    with pytest.raises(NoFaceFound):
        FaceCropper().crop(Image.new("RGB", (400, 400), (30, 160, 60)))


def test_the_crop_is_square_and_wider_than_the_detected_box(monkeypatch):
    """AFHQ crops take in the whole head. Matching that framing matters more
    than hugging the detector's eyes-to-chin box."""
    cropper = FaceCropper()
    monkeypatch.setattr(cropper, "detect", lambda image: (400.0, 400.0, 100.0, 100.0))

    cropped = cropper.crop(Image.new("RGB", (1000, 1000)))

    width, height = cropped.size
    assert width == height, "a non-square crop would be squashed by the centre-crop"
    assert width == pytest.approx(100 * (1 + 2 * DEFAULT_MARGIN), abs=1)


def test_a_face_at_the_edge_still_gets_a_full_square(monkeypatch):
    """Slide the window inside the frame rather than shrinking it, so an
    off-centre subject isn't penalised with less context."""
    cropper = FaceCropper()
    monkeypatch.setattr(cropper, "detect", lambda image: (0.0, 0.0, 100.0, 100.0))

    cropped = cropper.crop(Image.new("RGB", (1000, 1000)))

    assert cropped.size[0] == cropped.size[1]
    assert cropped.size[0] == pytest.approx(100 * (1 + 2 * DEFAULT_MARGIN), abs=1)


def test_the_crop_never_escapes_a_small_image(monkeypatch):
    cropper = FaceCropper()
    monkeypatch.setattr(cropper, "detect", lambda image: (10.0, 10.0, 80.0, 80.0))

    cropped = cropper.crop(Image.new("RGB", (100, 100)))

    assert cropped.size == (100, 100)


# ----------------------------------------------------------------- vectors


def test_a_vector_survives_a_round_trip_through_the_database_encoding():
    vector = np.random.default_rng(0).standard_normal(EMBEDDING_DIM).astype(np.float32)

    assert np.array_equal(unpack(pack(vector), EMBEDDING_DIM), vector)


def test_unpacking_the_wrong_width_is_caught_immediately():
    """A row embedded by a different model would otherwise broadcast silently."""
    with pytest.raises(ValueError, match="512-d"):
        unpack(pack(np.zeros(8, dtype=np.float32)), EMBEDDING_DIM)


def test_normalising_leaves_a_zero_vector_alone_rather_than_producing_nan():
    """One degenerate image must not poison the whole corpus matrix."""
    out = l2_normalize(np.zeros((1, 4), dtype=np.float32))

    assert not np.isnan(out).any()


# ----------------------------------------------------------------- matching


def test_a_match_names_a_dog_from_the_corpus(matcher, dog_corpus):
    result = matcher.match(Image.new("RGB", (300, 300), (200, 120, 60)))

    assert result.slug in dog_corpus
    assert 0.0 <= result.score <= 1.0
    assert len(result.shared_traits) <= 3
    assert set(result.shared_traits) <= set(attrs.LABELS)


def test_the_same_photo_always_gives_the_same_dog(matcher):
    """Stability matters for demos: a refresh must not reroll the answer."""
    image = Image.new("RGB", (300, 300), (10, 200, 90))

    first = matcher.match(image)
    second = matcher.match(image)

    assert (first.slug, first.shared_traits) == (second.slug, second.shared_traits)


def test_different_photos_do_not_all_collapse_onto_one_dog(matcher):
    """The failure this whole design exists to prevent.

    Without species-mean centring, CLIP's human/dog gap dominates every
    comparison and the *same* dog wins for everybody. Distinct inputs must
    reach more than one dog.
    """
    slugs = {
        matcher.match(Image.new("RGB", (256, 256), colour)).slug
        for colour in [(230, 40, 40), (40, 230, 40), (40, 40, 230), (240, 230, 30), (20, 20, 20)]
    }

    assert len(slugs) > 1, f"every photo matched the same dog: {slugs}"


def test_centring_actually_changes_the_outcome(matcher):
    """Guards the correction itself, not merely its presence.

    A regression that dropped the subtraction would pass every other test in
    this file — the matcher would still return dogs, just worse ones. Compared
    over a batch rather than one draw, because for any single embedding the two
    rankings can agree by chance.
    """
    rng = np.random.default_rng(3)
    embeddings = [
        l2_normalize(rng.standard_normal(EMBEDDING_DIM).astype(np.float32)) for _ in range(12)
    ]
    assert np.linalg.norm(matcher._human_embedding_mean) > 1e-6, "no mean to remove"

    centred = [matcher.match_embedding(e) for e in embeddings]
    matcher._human_embedding_mean = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    uncentred = [matcher.match_embedding(e) for e in embeddings]

    assert [(c.slug, c.score) for c in centred] != [(u.slug, u.score) for u in uncentred]


def test_shared_traits_need_both_sides_to_be_above_average(matcher):
    """`min` of the two z-scores, so 'unusually fluffy person, utterly average
    dog' is not reported as something they share."""
    matcher._human_attribute_mean = np.zeros(attrs.DIM, dtype=np.float32)
    matcher._human_attribute_std = np.ones(attrs.DIM, dtype=np.float32)

    # A human who is below average on everything can share nothing.
    human_z = np.full(attrs.DIM, -5.0, dtype=np.float32)
    assert matcher._shared_traits(human_z, winner=0) == []


def test_a_standout_match_scores_higher_than_a_muddle():
    """The displayed number is distinctiveness — how far the winner stands out
    from the rest of the corpus — so a runaway winner must outscore a tie."""
    standout = ml_matcher._distinctiveness(np.array([0.1, 0.1, 0.1, 0.9]), winner=3)
    muddle = ml_matcher._distinctiveness(np.array([0.50, 0.49, 0.48, 0.51]), winner=3)

    assert standout > muddle


def test_an_entirely_flat_corpus_does_not_divide_by_zero():
    assert ml_matcher._distinctiveness(np.full(5, 0.3), winner=0) == 0.5


# ------------------------------------------------------------- build guards


def test_building_without_embeddings_says_which_script_to_run(dog_corpus):
    """dog_corpus is ingested but not embedded — the state a VM is in right
    after seeding the images."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        with pytest.raises(ml_matcher.NotCalibrated, match="embed_dogs"):
            ml_matcher.DogMatcher.build(db, cropper=PassThroughCropper())
    finally:
        db.close()


def test_building_without_calibration_says_which_script_to_run(dog_corpus, tiny_encoder):
    import embed_dogs
    from app.database import SessionLocal

    embed_dogs.embed(encoder=tiny_encoder)

    db = SessionLocal()
    try:
        with pytest.raises(ml_matcher.NotCalibrated, match="calibrate_humans"):
            ml_matcher.DogMatcher.build(db, encoder=tiny_encoder, cropper=PassThroughCropper())
    finally:
        db.close()


def test_the_matcher_is_built_once_and_reused(matcher):
    """It parses a 350MB graph, so the workers must not each build their own."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        assert ml_matcher.get_matcher(db) is ml_matcher.get_matcher(db)
    finally:
        db.close()


def test_the_committed_prompt_vectors_match_the_vocabulary():
    """Edit attributes.py without re-running the export and every attribute
    score silently refers to the wrong word."""
    vectors = ml_matcher.load_text_vectors()

    assert vectors.shape == (attrs.DIM, EMBEDDING_DIM)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_the_attribute_vocabulary_is_near_orthogonal():
    """Guards the mean-centring in export_encoder.py.

    Raw CLIP text embeddings sit in a narrow cone — straight out of the model
    every pair here scored about +0.85, so sixteen "different" attributes were
    sixteen near-copies and each score mostly measured the cone. Drop the
    centring and this goes back to ~+0.85, which is a silent, serious
    degradation: matching would still run and still return dogs.
    """
    vectors = ml_matcher.load_text_vectors()
    similarity = vectors @ vectors.T
    off_diagonal = similarity[~np.eye(attrs.DIM, dtype=bool)]

    assert off_diagonal.mean() < 0.2, f"attributes are barely distinguishable: {off_diagonal.mean():.3f}"


def test_opposite_attributes_point_in_opposite_directions():
    """The sanity check the centring is *for*: if "fluffy" and "sleek" score
    alike, the attribute space carries no usable signal."""
    vectors = ml_matcher.load_text_vectors()
    similarity = vectors @ vectors.T
    index = {label: i for i, label in enumerate(attrs.LABELS)}

    opposed = similarity[index["fluffy"], index["sleek"]]
    related = similarity[index["fluffy"], index["shaggy hair"]]

    assert opposed < related, f"fluffy~sleek {opposed:.3f} should be below fluffy~shaggy {related:.3f}"
    assert opposed < 0.1


def test_embedding_is_skipped_the_second_time(dog_corpus, tiny_encoder):
    """Re-embedding 5,239 dogs on every run would make the pass unusable."""
    import embed_dogs

    first, _ = embed_dogs.embed(encoder=tiny_encoder)
    second, _ = embed_dogs.embed(encoder=tiny_encoder)

    assert first == len(dog_corpus)
    assert second == 0
