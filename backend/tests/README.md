# Game tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest                       # 52 tests, ~14s
pytest -k streak -v          # or a slice of them
```

`requirements-dev.txt` is separate from `requirements.txt` on purpose: `backend/Dockerfile`
installs only the latter, so pytest never ships in the production image. CI runs
these on every push.

Everything runs against a throwaway data directory and SQLite file (see
`conftest.py`), so real leaderboards are never touched, and each test starts with
empty rooms, runs and boards.

## The files

**`test_solo.py`** — Streak Survival: three lives, no clock, and the score being
how far you got. Includes the rules that are easy to get wrong later, like a bad
run not wiping out your best one, and a finished run becoming unplayable.

**`test_rooms.py`** — the multiplayer engine, via the `table` fixture: a real
`Hub` with a list-appending transport instead of sockets. That this fixture can
exist *at all* is the point of the transport seam described in `app/game/hub.py` —
if the game logic ever grows a dependency on WebSockets, these tests stop being
writable and the seam has leaked.

Covers what makes the mode server-authoritative: only your first answer counts,
faster correct answers score more, streaks add a bonus, the question closes early
once everyone has locked in, your choice stays secret until the reveal, only the
host can start or change settings, a dropped socket keeps your seat *and* score,
the host role is handed on, and an abandoned room is reaped.

**`test_api.py`** — the same thing end-to-end through the ASGI app: every REST
route with its failure cases, the socket refusing an unidentified client, and two
real WebSocket clients playing five rounds together.

## The answer oracle

`conftest.correct_choice()` derives the right answer from a question payload,
which a browser cannot do — the dummy pairing in `app/game/content.py` is salted
with `SECRET_KEY`. The tests get away with it only by running in the same process.

## Fixtures worth knowing

| Fixture | What you get |
| --- | --- |
| `table` | a `Hub` with fake transports and three players, no room yet |
| `lobby` | that hub plus a room all three have joined, still in the lobby |
| `in_play` | the same room mid-game, sitting on its first open question |
| `client` | `TestClient` over the real app (REST + WebSocket) |
| `fast_pacing` | shrinks countdown/reveal pauses; the question clock is untouched |
| `clean_game_state` | autouse; empties rooms, runs and leaderboards per test |
