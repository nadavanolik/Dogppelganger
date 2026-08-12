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

# Isolate every run: real leaderboards and databases are never touched.
_TMP = tempfile.mkdtemp(prefix="dogppelganger-test-")
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))
os.environ["GAME_DATA_DIR"] = str(Path(_TMP) / "gamedata")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TMP).as_posix()}/test.db")

from app.game import rooms, solo, store  # noqa: E402  (must follow the env setup)
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
def client():
    """Starlette's TestClient over the real ASGI app (REST + WebSocket)."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


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
