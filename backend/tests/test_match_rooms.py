"""Mix & Match rooms — the shared-board claim engine.

This is the file that covers ProjectPlan 2.10's requirement: several players act
on one board at the same time and the server has to keep them from ever believing
different things. Almost every test here is about a conflict.
"""
import asyncio

import pytest
from conftest import correct_dog, perfect_pairs, wait_for

from app.game import rooms, store


def board_of(client) -> dict:
    """The board as this player last saw it."""
    state = client.last("room_state")
    assert state is not None and state["board"], "no board in the last state"
    return state["board"]


def claims_of(client) -> set:
    state = client.last("room_state")
    return {(c["human"], c["dog"], c["playerId"]) for c in state["claims"]}


# --------------------------------------------------------------- dealing


async def test_the_board_opens_with_four_and_four(match_in_play):
    _hub, clients, room = match_in_play
    state = clients["p_a"].last("room_state")
    assert state["gameType"] == "match"
    assert len(state["board"]["humans"]) == 4
    assert len(state["board"]["dogs"]) == 4
    assert state["question"] is None  # the other game type's field stays empty


async def test_the_answer_key_stays_on_the_server_while_the_board_is_open(match_in_play):
    hub, clients, room = match_in_play
    state = hub.rooms.state(room)
    assert state["boardAnswer"] is None
    assert "answer" not in repr(state["board"])


# ----------------------------------------------------------- claiming


async def test_a_claim_is_acknowledged_and_broadcast(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=1)

    assert clients["p_a"].last("claim_ack") == {"human": 0, "dog": 1}
    # Everyone sees it, not just the claimer — that's the point of the mode.
    for client in clients.values():
        assert (0, 1, "p_a") in claims_of(client)


async def test_a_combination_can_only_be_held_by_one_player(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=2, dogSlot=3)
    clients["p_b"].drain()
    await clients["p_b"].send("claim", humanSlot=2, dogSlot=3)

    rejection = clients["p_b"].last("claim_rejected")
    assert rejection is not None
    assert rejection["human"] == 2 and rejection["dog"] == 3
    assert "ilona" in rejection["message"]  # told who beat them

    assert room.claims[(2, 3)] == "p_a"
    assert room.members["p_b"].pairs == {}


async def test_losing_a_race_still_leaves_both_tiles_playable(match_in_play):
    """Only the *combination* is taken. This is the rule the game turns on."""
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=0)
    await clients["p_b"].send("claim", humanSlot=0, dogSlot=0)  # denied

    # Same human, different dog — and same dog, different human — both fine.
    await clients["p_b"].send("claim", humanSlot=0, dogSlot=1)
    await clients["p_c"].send("claim", humanSlot=1, dogSlot=0)

    assert room.members["p_b"].pairs == {0: 1}
    assert room.members["p_c"].pairs == {1: 0}
    assert room.claims[(0, 0)] == "p_a"


async def test_the_whole_grid_can_be_shared_out(match_in_play):
    """Three players can hold three different dogs for the same human."""
    _, clients, room = match_in_play
    for index, player in enumerate(("p_a", "p_b", "p_c")):
        await clients[player].send("claim", humanSlot=3, dogSlot=index)
    assert {room.claims[(3, i)] for i in range(3)} == {"p_a", "p_b", "p_c"}


async def test_reclaiming_my_own_pair_is_not_an_error(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=2)
    clients["p_a"].drain()
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=2)

    assert clients["p_a"].last("claim_rejected") is None
    assert clients["p_a"].last("error") is None
    assert room.members["p_a"].pairs == {0: 2}


async def test_repairing_a_human_releases_the_old_combination(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=1)
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=2)

    assert room.members["p_a"].pairs == {0: 2}
    assert (0, 1) not in room.claims  # freed, not hoarded

    # And someone else can now take what was let go.
    await clients["p_b"].send("claim", humanSlot=0, dogSlot=1)
    assert room.claims[(0, 1)] == "p_b"


async def test_repairing_a_dog_releases_the_human_that_had_it(match_in_play):
    """A dog belongs to one human on my board, so this displaces the other pair."""
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=1)
    await clients["p_a"].send("claim", humanSlot=3, dogSlot=1)

    assert room.members["p_a"].pairs == {3: 1}
    assert (0, 1) not in room.claims
    assert room.claims[(3, 1)] == "p_a"


async def test_releasing_hands_a_combination_back(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=1, dogSlot=1)
    await clients["p_a"].send("release", humanSlot=1)

    assert room.members["p_a"].pairs == {}
    assert (1, 1) not in room.claims

    await clients["p_b"].send("claim", humanSlot=1, dogSlot=1)
    assert room.claims[(1, 1)] == "p_b"


async def test_you_cannot_release_someone_elses_claim(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=1, dogSlot=1)
    await clients["p_b"].send("release", humanSlot=1)

    assert room.claims[(1, 1)] == "p_a"


async def test_claims_off_the_board_are_refused(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=9, dogSlot=0)
    assert "person" in clients["p_a"].last("error")["message"]

    await clients["p_a"].send("claim", humanSlot=0, dogSlot=9)
    assert "dog" in clients["p_a"].last("error")["message"]
    assert room.claims == {}


# ------------------------------------------------------------ submitting


async def test_submitting_freezes_your_board(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=0)
    await clients["p_a"].send("submit")

    assert room.members["p_a"].submitted is True
    await clients["p_a"].send("claim", humanSlot=1, dogSlot=1)
    assert "submitted" in clients["p_a"].last("error")["message"]
    assert room.members["p_a"].pairs == {0: 0}


async def test_a_submitted_board_keeps_holding_its_claims(match_in_play):
    """Otherwise submitting early would hand your work to everyone else."""
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=0)
    await clients["p_a"].send("submit")

    await clients["p_b"].send("claim", humanSlot=0, dogSlot=0)
    assert clients["p_b"].last("claim_rejected") is not None


async def test_the_round_closes_as_soon_as_everyone_submits(match_in_play):
    """The clock is 30s; this has to land in a fraction of that."""
    _, clients, room = match_in_play
    for client in clients.values():
        await client.send("submit")
    assert await wait_for(lambda: room.phase == "reveal", timeout=2)


async def test_the_round_closes_on_the_clock_if_someone_never_submits(match_lobby):
    hub, clients, room = match_lobby
    # Below the 30s a host is allowed to pick, so set it straight on the room —
    # and before `start`, so the game loop can't read the old value first.
    room.seconds_per_question = 1
    await clients["p_a"].send("start")
    assert await wait_for(lambda: room.phase == "question")

    await clients["p_a"].send("submit")  # p_b and p_c just sit there
    assert await wait_for(lambda: room.phase == "reveal", timeout=6)


async def test_players_see_who_is_still_deciding(match_in_play):
    hub, clients, room = match_in_play
    await clients["p_a"].send("submit")
    state = hub.rooms.state(room)
    done = {p["playerId"]: p["submitted"] for p in state["players"]}
    assert done == {"p_a": True, "p_b": False, "p_c": False}


# --------------------------------------------------------------- scoring


async def test_a_perfect_board_scores_every_pair_plus_the_bonus(match_in_play):
    _, clients, room = match_in_play
    board = board_of(clients["p_a"])
    for human, dog in perfect_pairs(board).items():
        await clients["p_a"].send("claim", humanSlot=human, dogSlot=dog)
    await clients["p_a"].send("submit")
    await clients["p_b"].send("submit")
    await clients["p_c"].send("submit")

    assert await wait_for(lambda: room.phase == "reveal")
    me = room.members["p_a"]
    assert me.last_round_correct == 4
    # Four pairs claimed immediately, so each is worth close to the maximum.
    lowest = 4 * rooms.MATCH_BASE_PER_PAIR + rooms.MATCH_PERFECT_BONUS
    assert lowest < me.score <= 4 * (rooms.MATCH_BASE_PER_PAIR + rooms.MATCH_SPEED_MAX) + (
        rooms.MATCH_PERFECT_BONUS
    )
    assert me.streak == 1


async def test_wrong_pairs_are_worth_nothing_and_carry_no_penalty(match_in_play):
    _, clients, room = match_in_play
    board = board_of(clients["p_a"])
    right = correct_dog(board, 0)
    wrong = (right + 1) % 4
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=wrong)
    for client in clients.values():
        await client.send("submit")

    assert await wait_for(lambda: room.phase == "reveal")
    assert room.members["p_a"].last_round_correct == 0
    assert room.members["p_a"].score == 0


async def test_claiming_sooner_is_worth_more(match_in_play):
    _, clients, room = match_in_play
    board = board_of(clients["p_a"])
    # Two players can't hold the same combination, so give them different humans
    # and compare like for like. The gap has to clear the 10-point rounding:
    # against a 30s round, 1.5s is worth about 15 points.
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=correct_dog(board, 0))
    await asyncio.sleep(1.5)
    await clients["p_b"].send("claim", humanSlot=1, dogSlot=correct_dog(board, 1))
    for client in clients.values():
        await client.send("submit")

    assert await wait_for(lambda: room.phase == "reveal")
    assert room.members["p_a"].score > room.members["p_b"].score
    assert room.members["p_a"].last_round_correct == 1
    assert room.members["p_b"].last_round_correct == 1


async def test_three_right_is_impossible_so_the_streak_breaks_on_any_slip(match_in_play):
    _, clients, room = match_in_play
    board = board_of(clients["p_a"])
    pairs = perfect_pairs(board)
    pairs[0], pairs[1] = pairs[1], pairs[0]  # the smallest possible mistake
    for human, dog in pairs.items():
        await clients["p_a"].send("claim", humanSlot=human, dogSlot=dog)
    for client in clients.values():
        await client.send("submit")

    assert await wait_for(lambda: room.phase == "reveal")
    assert room.members["p_a"].last_round_correct == 2
    assert room.members["p_a"].streak == 0


async def test_the_answer_is_revealed_only_once_the_round_is_closed(match_in_play):
    hub, clients, room = match_in_play
    assert hub.rooms.state(room)["boardAnswer"] is None
    for client in clients.values():
        await client.send("submit")

    assert await wait_for(lambda: room.phase == "reveal")
    revealed = clients["p_a"].last("question_end")
    assert revealed["boardAnswer"] is not None
    assert {int(k): v for k, v in revealed["boardAnswer"].items()} == room.board.answer


# --------------------------------------------------- leaving and finishing


async def test_leaving_for_good_frees_your_claims(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=0)
    await clients["p_a"].send("leave")

    assert (0, 0) not in room.claims
    await clients["p_b"].send("claim", humanSlot=0, dogSlot=0)
    assert room.claims[(0, 0)] == "p_b"


async def test_a_dropped_socket_keeps_your_claims_but_does_not_stall_the_round(match_in_play):
    """A refresh shouldn't cost you the board, and shouldn't hold everyone up."""
    hub, clients, room = match_in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=0)
    await hub.on_disconnect("p_a")

    assert room.claims[(0, 0)] == "p_a"  # seat held, claims held
    await clients["p_b"].send("submit")
    await clients["p_c"].send("submit")
    assert await wait_for(lambda: room.phase == "reveal")


async def test_a_finished_game_lands_on_the_match_leaderboard(match_lobby):
    hub, clients, room = match_lobby
    room.rounds_total = 1  # below the host's minimum of 5; one board is enough here
    await clients["p_a"].send("start")
    assert await wait_for(lambda: room.phase == "question")
    # The phase flips just before the broadcast — wait for the board to land.
    assert await wait_for(lambda: (clients["p_a"].last("room_state") or {}).get("board"))

    board = board_of(clients["p_a"])
    for human, dog in perfect_pairs(board).items():
        await clients["p_a"].send("claim", humanSlot=human, dogSlot=dog)
    for client in clients.values():
        await client.send("submit")

    assert await wait_for(lambda: room.phase == "over", timeout=6)
    match_board = store.top(store.BOARD_MULTIPLAYER_MATCH)
    assert [e["playerId"] for e in match_board][:1] == ["p_a"]
    # And nothing leaked onto the Kahoot board.
    assert store.top(store.BOARD_MULTIPLAYER) == []


# ------------------------------------------------- the two types stay apart


async def test_claiming_in_a_kahoot_room_is_refused(in_play):
    _, clients, room = in_play
    await clients["p_a"].send("claim", humanSlot=0, dogSlot=0)
    assert "Mix & Match" in clients["p_a"].last("error")["message"]


async def test_answering_in_a_match_room_is_refused(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("answer", questionIndex=0, choice=0)
    assert clients["p_a"].last("answer_rejected") is not None


async def test_switching_the_game_type_resets_the_clock(lobby):
    hub, clients, room = lobby
    await clients["p_a"].send("set_options", secondsPerQuestion=10)
    await clients["p_a"].send("set_options", gameType="match")

    assert room.game_type == "match"
    # 10 seconds is unplayable for a four-pair board, so it snaps to the match scale.
    assert room.seconds_per_question == rooms.MATCH_DEFAULT_SECONDS

    await clients["p_a"].send("set_options", secondsPerQuestion=10)
    assert "30 or 45 or 60" in clients["p_a"].last("error")["message"]


async def test_the_game_type_is_locked_once_a_game_starts(match_in_play):
    _, clients, room = match_in_play
    await clients["p_a"].send("set_options", gameType="double")
    assert "locked" in clients["p_a"].last("error")["message"]
    assert room.game_type == "match"


@pytest.mark.parametrize("bad", ["", "kahoot", "MATCH"])
async def test_unknown_game_types_are_refused(table, bad):
    hub, _clients = table
    with pytest.raises(ValueError):
        hub.rooms.create("x", "p_a", "ilona", bad)
