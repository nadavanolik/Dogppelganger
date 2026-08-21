"""The real endpoints: /api/game/* and the /api/game/ws socket.

Driven through Starlette's TestClient against the actual ASGI app, so routing,
validation, the socket handshake and the identity check are all exercised for
real — only the network hop is simulated.
"""
import pytest
from conftest import correct_choice, perfect_pairs
from starlette.websockets import WebSocketDisconnect


def read_until(ws, predicate, limit: int = 80):
    """Pull messages until one matches, so broadcasts can't desynchronise us."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    return None


# Two real accounts. Players are logged-in users now — the server derives the
# player id from the token instead of believing a `playerId` in the body — so
# every test that used to invent "http_a" signs somebody in instead.


@pytest.fixture
def player_a(user_factory):
    return user_factory()


@pytest.fixture
def player_b(user_factory):
    return user_factory()


def socket_url(player, path: str = "/api/game/ws") -> str:
    """A socket URL for a player. The token goes in the query string because a
    browser cannot set headers on a WebSocket handshake."""
    return f"{path}?token={player['token']}"


@pytest.fixture
def room(client, player_a):
    res = client.post(
        "/api/game/rooms",
        json={"name": "Test room"},
        headers=player_a["headers"],
    )
    assert res.status_code == 201
    return res.json()


# ------------------------------------------------------------------ REST


@pytest.fixture
def match_room(client, player_a):
    res = client.post(
        "/api/game/rooms",
        json={"name": "Match room", "gameType": "match"},
        headers=player_a["headers"],
    )
    assert res.status_code == 201
    return res.json()


def test_creating_a_room_returns_its_code(room):
    assert len(room["code"]) == 4
    assert room["phase"] == "lobby"
    assert room["gameType"] == "double", "the Kahoot game stays the default"
    assert room["playerCount"] == 0, "the host joins over the socket, like everyone else"


def test_a_match_room_is_created_with_its_own_defaults(match_room):
    assert match_room["gameType"] == "match"
    assert match_room["secondsPerQuestion"] == 45, "a four-pair board needs longer"
    assert match_room["roundsTotal"] == 5


def test_an_unknown_game_type_is_refused(client, player_a):
    res = client.post(
        "/api/game/rooms",
        json={"gameType": "kahoot"},
        headers=player_a["headers"],
    )
    assert res.status_code == 422


def test_a_created_room_shows_up_in_the_public_list(client, room):
    listing = client.get("/api/game/rooms").json()

    assert any(r["id"] == room["id"] for r in listing["rooms"])
    assert listing["options"]["seconds"] == [10, 15, 20]
    assert listing["options"]["matchSeconds"] == [30, 45, 60]
    assert listing["options"]["gameTypes"] == ["double", "match"]
    assert listing["options"]["rounds"][0] == 5


def test_a_room_can_be_found_by_its_code(client, room):
    found = client.get(f"/api/game/rooms/by-code/{room['code'].lower()}")

    assert found.status_code == 200
    assert found.json()["id"] == room["id"]


def test_room_state_is_served_by_id(client, room):
    state = client.get(f"/api/game/rooms/{room['id']}").json()

    assert state["phase"] == "lobby"
    assert state["question"] is None


@pytest.mark.parametrize(
    "path",
    ["/api/game/rooms/by-code/ZZZZ", "/api/game/rooms/does-not-exist", "/api/game/leaderboard/nope"],
)
def test_missing_things_404(client, path):
    assert client.get(path).status_code == 404


def test_creating_a_room_needs_a_login(client):
    """Was 'a room needs a playerId'. There is no such field any more — the
    player is whoever holds the token, so the failure mode is 401, not 422."""
    res = client.post("/api/game/rooms", json={"name": "x"})

    assert res.status_code == 401


def test_a_solo_run_can_be_played_over_rest(client, player_a):
    run = client.post("/api/game/solo/start", headers=player_a["headers"]).json()
    assert run["question"] is not None and run["lives"] == 3

    choice = correct_choice(run["question"])
    result = client.post(
        "/api/game/solo/answer",
        json={"runToken": run["runToken"], "choice": choice},
        headers=player_a["headers"],
    ).json()

    assert result["wasCorrect"] is True
    assert result["score"] == 1
    assert result["answerIndex"] == choice


def test_a_bogus_run_token_is_a_404(client, player_a):
    res = client.post(
        "/api/game/solo/answer",
        json={"runToken": "xxx", "choice": 0},
        headers=player_a["headers"],
    )

    assert res.status_code == 404
    assert "start a new one" in res.json()["detail"]


def test_someone_elses_run_is_a_404(client, player_a, player_b):
    """A run token is not a bearer credential.

    Before, anyone holding the token could answer for the run and put a score
    on the board under the owner's name.
    """
    run = client.post("/api/game/solo/start", headers=player_a["headers"]).json()
    choice = correct_choice(run["question"])

    res = client.post(
        "/api/game/solo/answer",
        json={"runToken": run["runToken"], "choice": choice},
        headers=player_b["headers"],
    )

    assert res.status_code == 404


def test_a_solo_match_run_can_be_played_over_rest(client, player_a):
    run = client.post("/api/game/solo/match/start", headers=player_a["headers"]).json()
    assert run["lives"] == 3
    assert len(run["board"]["humans"]) == 4

    result = client.post(
        "/api/game/solo/match/submit",
        json={"runToken": run["runToken"], "pairs": perfect_pairs(run["board"])},
        headers=player_a["headers"],
    ).json()

    assert result["wasPerfect"] is True
    assert result["score"] == 4
    assert result["lives"] == 3
    assert result["board"] is not None


def test_a_solo_match_board_rejects_a_shared_dog(client, player_a):
    run = client.post("/api/game/solo/match/start", headers=player_a["headers"]).json()
    res = client.post(
        "/api/game/solo/match/submit",
        json={"runToken": run["runToken"], "pairs": {"0": 1, "2": 1}},
        headers=player_a["headers"],
    )

    assert res.status_code == 422
    assert "one person" in res.json()["detail"]


def test_a_bogus_match_token_is_a_404(client, player_a):
    res = client.post(
        "/api/game/solo/match/submit",
        json={"runToken": "xxx", "pairs": {}},
        headers=player_a["headers"],
    )

    assert res.status_code == 404


@pytest.mark.parametrize(
    "board", ["solo", "multiplayer", "solo_match", "multiplayer_match"]
)
def test_both_leaderboards_serve(client, board):
    res = client.get(f"/api/game/leaderboard/{board}").json()

    assert res["board"] == board
    assert isinstance(res["entries"], list)


# -------------------------------------------------------------- WebSocket


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("/api/game/ws", id="no identity at all"),
        pytest.param("/api/game/ws?token=not-a-real-jwt", id="a token that doesn't verify"),
    ],
)
def test_the_socket_refuses_an_unidentified_client(client, url):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url):
            pass


def test_two_players_can_play_a_game_over_the_socket(client, room, fast_pacing, player_a, player_b):
    with client.websocket_connect(socket_url(player_a)) as a:
        with client.websocket_connect(socket_url(player_b)) as b:
            assert a.receive_json()["type"] == "connected"
            assert b.receive_json()["type"] == "connected"

            a.send_json({"type": "game_join", "payload": {"roomId": room["id"]}})
            b.send_json({"type": "game_join", "payload": {"code": room["code"]}})

            joined = read_until(
                b, lambda m: m["type"] == "room_state" and len(m["payload"]["players"]) == 2
            )
            assert joined is not None, "both players should end up in the same room"
            # The host id is the creator's user id, as a string.
            assert joined["payload"]["hostId"] == str(player_a["id"])

            # Host-only rules hold over the wire, not just in the engine.
            b.send_json({"type": "game_start", "payload": {}})
            refused = read_until(b, lambda m: m["type"] == "error")
            assert refused["payload"]["message"] == "Only the host can do that."

            a.send_json({"type": "game_set_options", "payload": {"roundsTotal": 5}})
            a.send_json({"type": "game_start", "payload": {}})

            for round_no in range(5):
                opened = read_until(
                    a, lambda m: m["type"] == "room_state" and m["payload"]["phase"] == "question"
                )
                assert opened is not None, f"round {round_no} never opened"
                question = opened["payload"]["question"]
                assert len(question["options"]) == 4
                assert opened["payload"]["answerIndex"] is None, "no peeking mid-question"

                choice = correct_choice(question)
                answer = {"questionIndex": question["index"], "choice": choice}
                a.send_json({"type": "game_answer", "payload": answer})
                read_until(
                    b, lambda m: m["type"] == "room_state" and m["payload"]["phase"] == "question"
                )
                b.send_json({"type": "game_answer", "payload": answer})

                end = read_until(a, lambda m: m["type"] == "question_end")
                assert end is not None, f"round {round_no} never closed"
                assert end["payload"]["answerIndex"] == choice, "the answer comes out at the reveal"
                assert all(p["lastAward"] > 0 for p in end["payload"]["players"])

            over = read_until(a, lambda m: m["type"] == "game_over")
            assert over is not None
            assert over["payload"]["players"][0]["score"] > 0
            assert "leaderboard" in over["payload"], "the all-time board rides along"


def test_two_players_race_for_the_same_pair_over_the_socket(client, match_room, fast_pacing, player_a, player_b):
    """The end-to-end version of ProjectPlan 2.10: one board, two players, one
    combination — and the server deciding who gets it."""
    with client.websocket_connect(socket_url(player_a)) as a:
        with client.websocket_connect(socket_url(player_b)) as b:
            a.receive_json()
            b.receive_json()
            a.send_json({"type": "game_join", "payload": {"roomId": match_room["id"]}})
            b.send_json({"type": "game_join", "payload": {"code": match_room["code"]}})
            read_until(b, lambda m: m["type"] == "room_state" and len(m["payload"]["players"]) == 2)

            a.send_json({"type": "game_start", "payload": {}})
            opened = read_until(
                a, lambda m: m["type"] == "room_state" and m["payload"]["phase"] == "question"
            )
            assert opened is not None, "the board never opened"
            board = opened["payload"]["board"]
            assert len(board["humans"]) == 4 and len(board["dogs"]) == 4
            assert opened["payload"]["boardAnswer"] is None, "no peeking mid-round"

            answers = perfect_pairs(board)
            contested = {"humanSlot": 0, "dogSlot": answers[0]}

            a.send_json({"type": "game_claim", "payload": contested})
            assert read_until(a, lambda m: m["type"] == "claim_ack") is not None

            # b goes for the same combination and is told who beat them.
            read_until(b, lambda m: m["type"] == "room_state" and m["payload"]["claims"])
            b.send_json({"type": "game_claim", "payload": contested})
            rejected = read_until(b, lambda m: m["type"] == "claim_rejected")
            assert rejected is not None
            # Named by their real username, which now comes from the database
            # rather than from a `name` the browser supplied.
            assert player_a["username"] in rejected["payload"]["message"]

            # The human is still playable for b — just not with that dog.
            other = (answers[0] + 1) % 4
            b.send_json({"type": "game_claim", "payload": {"humanSlot": 0, "dogSlot": other}})
            assert read_until(b, lambda m: m["type"] == "claim_ack") is not None

            a.send_json({"type": "game_submit", "payload": {}})
            b.send_json({"type": "game_submit", "payload": {}})

            end = read_until(a, lambda m: m["type"] == "question_end")
            assert end is not None, "the round never closed"
            assert end["payload"]["boardAnswer"] is not None, "the key comes out at the reveal"
            scores = {p["playerId"]: p["lastAward"] for p in end["payload"]["players"]}
            assert scores[str(player_a["id"])] > 0, "a right pair scores"
            assert scores[str(player_b["id"])] == 0, "a wrong pair doesn't"


def test_the_clock_is_the_servers(client, room, player_a):
    """Clients are told the server's `now`, so their countdowns can't drift."""
    with client.websocket_connect(socket_url(player_a)) as a:
        a.receive_json()
        a.send_json({"type": "game_join", "payload": {"roomId": room["id"]}})
        state = read_until(a, lambda m: m["type"] == "room_state")

        assert isinstance(state["payload"]["serverNow"], int)

        a.send_json({"type": "game_ping", "payload": {}})
        pong = read_until(a, lambda m: m["type"] == "pong")
        assert isinstance(pong["payload"]["serverNow"], int)
