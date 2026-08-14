# Game tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest                       # 119 tests, ~20s
pytest -k claim -v           # or a slice of them
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
exist _at all_ is the point of the transport seam described in `app/game/hub.py` —
if the game logic ever grows a dependency on WebSockets, these tests stop being
writable and the seam has leaked.

Covers what makes the mode server-authoritative: only your first answer counts,
faster correct answers score more, streaks add a bonus, the question closes early
once everyone has locked in, your choice stays secret until the reveal, only the
host can start or change settings, a dropped socket keeps your seat _and_ score,
the host role is handed on, and an abandoned room is reaped.

**`test_board.py`** — dealing and marking a Mix & Match board, with no event loop
in sight. Includes the parity fact the solo lives rule rests on: matching four
humans to four distinct dogs, you can never be wrong on exactly one, so the wrong
count is always 0, 2, 3 or 4.

**`test_match_rooms.py`** — the claim engine, and the file that covers
ProjectPlan 2.10. Nearly every test is a conflict: two players going for the same
combination and only one getting it, the loser still being free to use either
tile in a _different_ combination, releasing handing a combination back,
re-pairing displacing your own claim rather than someone else's, a submitted
board staying frozen and keeping its claims, the round closing early when
everyone submits and on the clock when they don't, and leaving for good freeing
what you held while a dropped socket does not.

**`test_solo_match.py`** — three lives, no clock, one life per imperfect board,
and each mode's score staying on its own leaderboard.

**`test_api.py`** — the same things end-to-end through the ASGI app: every REST
route with its failure cases, the socket refusing an unidentified client, two
real WebSocket clients playing five rounds of Spot the Double, and two racing for
the same pairing in a Mix & Match room.

## The answer oracle

`conftest.correct_choice()` derives the right answer from a question payload, and
`correct_dog()` / `perfect_pairs()` do the same for a board. A browser cannot:
the dummy pairing in `app/game/content.py` is salted with `SECRET_KEY`. The tests
get away with it only by running in the same process.

## Fixtures worth knowing

| Fixture            | What you get                                                  |
| ------------------ | ------------------------------------------------------------- |
| `table`            | a `Hub` with fake transports and three players, no room yet   |
| `lobby`            | that hub plus a Spot the Double room all three have joined    |
| `in_play`          | the same room mid-game, sitting on its first open question    |
| `match_lobby`      | as `lobby`, but a Mix & Match room                            |
| `match_in_play`    | the same, mid-game, with the board open _and broadcast_       |
| `client`           | `TestClient` over the real app (REST + WebSocket)             |
| `fast_pacing`      | shrinks countdown/reveal pauses; the round clock is untouched |
| `clean_game_state` | autouse; empties rooms, runs and leaderboards per test        |

One trap worth knowing: the room's phase flips to `question` just _before_ the
open-board broadcast goes out, so waiting on `room.phase` alone races the message
into the inboxes. `match_in_play` waits for the board to actually land, and any
test that starts a game by hand needs to do the same before reading a client's
`room_state`.
