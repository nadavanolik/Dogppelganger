"""Shared fixtures for the game tests.

Loaded by pytest before any test module, which matters: ``app.game.store`` reads
its leaderboard snapshot at import time, so the environment has to point at a
throwaway directory *first*.
"""
import asyncio
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
# The one-off scripts aren't a package; tests import them by name.
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

# Isolate every run: real leaderboards and databases are never touched.
_TMP = tempfile.mkdtemp(prefix="dogppelganger-test-")
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))
os.environ["GAME_DATA_DIR"] = str(Path(_TMP) / "gamedata")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TMP).as_posix()}/test.db")
# Image storage lands in the same throwaway tree — no volume, no real corpus.
# Set before app.storage.layout is imported anywhere, for the same reason as
# GAME_DATA_DIR above.
os.environ["DOG_DATA_DIR"] = str(Path(_TMP) / "dogs")
os.environ["UPLOAD_DATA_DIR"] = str(Path(_TMP) / "uploads")

from app.game import rooms, solo, solo_match, store  # noqa: E402  (must follow the env setup)
from app.game.hub import Hub, Player  # noqa: E402


@pytest.fixture(autouse=True)
def clean_game_state():
    """Give each test empty rooms, runs and leaderboards.

    Game state is module-level (single worker, in memory), so without this the
    tests would see each other's scores. Reaching into the privates is the price
    of not adding a reset API that only tests would use.
    """
    from app.game.hub import hub as singleton_hub

    def reset():
        solo._runs.clear()
        solo_match._runs.clear()
        for board in store.BOARDS:
            store._state.boards[board] = {}
        # The API tests go through the module-level hub, so drop its rooms too.
        # No need to cancel their loops: the TestClient's event loop is gone by
        # the time we get here, and its tasks with it.
        singleton_hub.rooms.rooms.clear()
        singleton_hub.rooms._by_code.clear()

    reset()
    yield
    reset()


@pytest.fixture
def fast_pacing(monkeypatch):
    """Shrink the countdown and reveal pauses; the question clock is untouched."""
    monkeypatch.setattr(rooms, "COUNTDOWN_SECONDS", 0.05)
    monkeypatch.setattr(rooms, "REVEAL_SECONDS", 0.05)


class FakeClient:
    """A player whose 'socket' is a list of received messages."""

    def __init__(self, hub: Hub, player_id: str, name: str) -> None:
        self.hub = hub
        self.player = Player(id=player_id, name=name)
        self.inbox: list[dict] = []

    async def send(self, kind: str, **payload) -> None:
        """Act as this player. `kind` is the event name without the game_ prefix."""
        await self.hub.handle(self.player, {"type": f"game_{kind}", "payload": payload})

    def last(self, kind: str) -> dict | None:
        """The most recent payload of a given event type, or None."""
        for message in reversed(self.inbox):
            if message["type"] == kind:
                return message["payload"]
        return None

    def drain(self) -> None:
        self.inbox.clear()


@pytest.fixture
def table():
    """A hub wired to fake transports, plus three players ready to join.

    That this fixture can exist at all is the point of the transport seam in
    ``app/game/hub.py``: no WebSocket, no server, just game logic.
    """
    hub = Hub()
    clients: dict[str, FakeClient] = {}

    async def transport(player_id: str, message: dict) -> None:
        if player_id in clients:
            clients[player_id].inbox.append(message)

    hub.bind(transport)
    for player_id, name in (("p_a", "ilona"), ("p_b", "michal"), ("p_c", "nadav")):
        clients[player_id] = FakeClient(hub, player_id, name)
    return hub, clients


async def wait_for(predicate, timeout: float = 8.0) -> bool:
    """Poll until `predicate()` is true. The server drives the game, so tests
    watch for state changes rather than assuming they've already happened."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


@pytest.fixture
async def lobby(table, fast_pacing):
    """A room with all three players in it, still in the lobby."""
    hub, clients = table
    room = hub.rooms.create("Sunday puppy jam", "p_a", "ilona")
    for client in clients.values():
        await client.send("join", roomId=room.id)
    for client in clients.values():
        client.drain()

    yield hub, clients, room

    # Don't leave a game loop pending when the event loop closes.
    if room.task and not room.task.done():
        room.task.cancel()


@pytest.fixture
async def in_play(lobby):
    """The same room, mid-game, sitting on its first open question."""
    hub, clients, room = lobby
    await clients["p_a"].send("set_options", roundsTotal=5, secondsPerQuestion=10)
    await clients["p_a"].send("start")
    assert await wait_for(lambda: room.phase == "question"), "the first question never opened"
    for client in clients.values():
        client.drain()
    return hub, clients, room


@pytest.fixture
async def match_lobby(table, fast_pacing):
    """A Mix & Match room with all three players in it, still in the lobby."""
    hub, clients = table
    room = hub.rooms.create("Mix it up", "p_a", "ilona", rooms.GAME_MATCH)
    for client in clients.values():
        await client.send("join", roomId=room.id)
    for client in clients.values():
        client.drain()

    yield hub, clients, room

    if room.task and not room.task.done():
        room.task.cancel()


@pytest.fixture
async def match_in_play(match_lobby):
    """The same room, mid-game, sitting on its first open board."""
    hub, clients, room = match_lobby
    await clients["p_a"].send("set_options", roundsTotal=5, secondsPerQuestion=30)
    await clients["p_a"].send("start")
    assert await wait_for(lambda: room.phase == "question"), "the first board never opened"
    # The phase flips just *before* the broadcast, so waiting on the room object
    # alone would race the message into the inboxes. These tests read what the
    # players actually saw, so wait for the board to land — and don't drain it.
    assert await wait_for(
        lambda: all((c.last("room_state") or {}).get("board") for c in clients.values())
    ), "the open board was never broadcast"
    return hub, clients, room


@pytest.fixture
def client():
    """Starlette's TestClient over the real ASGI app (REST + WebSocket)."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------------ images
#
# The dog corpus is ~226MB and deliberately not in git (DATA_STORAGE.md §5.1),
# so the storage tests build their own images instead. Synthetic ones are
# strictly better here: no binaries in the repo, no download in CI, and a
# gradient of a known size is easier to assert on than a photo of a dog.


def make_image(
    width: int = 600,
    height: int = 400,
    fmt: str = "JPEG",
    *,
    colour: tuple[int, int, int] = (200, 120, 60),
    mode: str = "RGB",
    exif: bool = False,
) -> bytes:
    """Encoded image bytes, deterministic for a given set of arguments."""
    from io import BytesIO

    from PIL import Image

    image = Image.new(mode, (width, height), colour if mode != "RGBA" else (*colour, 128))
    buffer = BytesIO()
    if exif:
        # Orientation=6 means "rotate 90° CW to display", the tag phones set
        # when you shoot in portrait. decode() must apply it and then drop it.
        tags = Image.Exif()
        tags[0x0112] = 6
        image.save(buffer, fmt, exif=tags)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()


TINY_ENCODER = Path(__file__).parent / "fixtures" / "tiny_image_encoder.onnx"


class PassThroughCropper:
    """Stands in for FaceCropper where the test isn't about face detection.

    Synthetic images have no faces in them, and YuNet is quite right to say so.
    Tests that care about detection use the real cropper; tests about the
    matcher's arithmetic use this so they aren't blocked on having photographs
    of real people committed to the repository.
    """

    def crop(self, image, margin=None):
        return image


@pytest.fixture
def tiny_encoder():
    """A 6KB ONNX graph in place of CLIP's 350MB one.

    It reduces an image to its mean RGB and projects that to 512 dimensions:
    deterministic, content-dependent, and enough to exercise every line of the
    matcher. The real encoder is gitignored (see .gitignore), so CI could not
    use it even if the runtime were acceptable — and testing our arithmetic is
    the point here, not testing OpenAI's weights.
    """
    from app.ml.encoder import ClipImageEncoder

    return ClipImageEncoder(TINY_ENCODER)


@pytest.fixture
def matcher(dog_corpus, tiny_encoder):
    """A built matcher over the synthetic corpus, with detection stubbed out.

    Runs the real embed and calibrate passes rather than inserting vectors by
    hand, so the fixture keeps those two scripts honest as well.
    """
    import calibrate_humans
    import embed_dogs
    from app.database import SessionLocal
    from app.ml import matcher as ml_matcher

    embed_dogs.embed(encoder=tiny_encoder)

    faces = Path(tempfile.mkdtemp(prefix="faces-", dir=_TMP))
    for i in range(60):
        (faces / f"face_{i:03d}.jpg").write_bytes(
            make_image(200, 200, colour=(3 * i + 20, 200 - 2 * i, 90 + i))
        )
    calibrate_humans.calibrate(
        faces, encoder=tiny_encoder, cropper=PassThroughCropper(), min_samples=10
    )

    db = SessionLocal()
    try:
        built = ml_matcher.DogMatcher.build(
            db, encoder=tiny_encoder, cropper=PassThroughCropper()
        )
    finally:
        db.close()

    ml_matcher.reset()
    ml_matcher._matcher = built  # what get_matcher() will hand out
    yield built

    ml_matcher.reset()
    # The calibration row outlives dog_corpus's cleanup, so a later test that
    # asserts "not calibrated yet" would otherwise find this one and pass for
    # the wrong reason — or fail, depending on ordering.
    from app.models import Calibration

    db = SessionLocal()
    try:
        db.query(Calibration).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def dog_corpus():
    """Ingest a handful of synthetic 'dogs' and return their slugs.

    Uses the real ingest path rather than inserting rows directly, so the
    tests that depend on a populated corpus also keep the script honest.
    """
    import shutil

    from app.database import Base, SessionLocal, engine
    from app.models import DogAsset

    import ingest_dogs

    Base.metadata.create_all(bind=engine)
    source = Path(tempfile.mkdtemp(prefix="dogsrc-", dir=_TMP))
    for i in range(5):
        (source / f"flickr_dog_{i:06d}.jpg").write_bytes(
            make_image(320, 320, colour=(40 * i + 10, 90, 140))
        )

    # Single worker: a process pool inside pytest costs more in spawn time than
    # five 320px images cost to resize.
    ingest_dogs.ingest(source, limit=None, workers=1)
    db = SessionLocal()
    try:
        slugs = ingest_dogs.assign_manifest_indices(db)
    finally:
        db.close()

    yield slugs

    db = SessionLocal()
    try:
        db.query(DogAsset).delete()
        db.commit()
    finally:
        db.close()
    shutil.rmtree(source, ignore_errors=True)
    shutil.rmtree(Path(os.environ["DOG_DATA_DIR"]), ignore_errors=True)


def correct_choice(question: dict) -> int:
    """Work out the right answer for a question payload.

    Only possible in-process: the dummy pairing in ``app/game/content.py`` is
    salted with SECRET_KEY, so a browser can't recompute it.
    """
    from app.game import content

    for i, dog_index in enumerate(question["options"]):
        if content._human_seed_for(dog_index) == question["humanSeed"]:
            return i
    raise AssertionError(f"no correct option among {question['options']}")


def correct_dog(board_payload: dict, human_slot: int) -> int:
    """Which dog slot belongs to a human slot, from the client-safe board payload.

    The same oracle as `correct_choice`, and possible for the same reason: the
    dummy pairing is salted with SECRET_KEY, so only in-process code can do this.
    """
    from app.game import content

    human = board_payload["humans"][human_slot]
    for dog in board_payload["dogs"]:
        if content._human_seed_for(dog["dogIndex"]) == human["humanSeed"]:
            return dog["slot"]
    raise AssertionError(f"no dog on the board matches human {human_slot}")


def perfect_pairs(board_payload: dict) -> dict[int, int]:
    """The whole answer key for a board, worked out from the payload."""
    return {h["slot"]: correct_dog(board_payload, h["slot"]) for h in board_payload["humans"]}
