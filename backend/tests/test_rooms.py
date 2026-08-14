"""Multiplayer rooms: the server owns the clock, the answer key and the truth.

Every test here runs the real game engine with a fake transport (see the `table`
fixture), so it exercises the actual state machine without a socket in sight.
"""
import asyncio

import pytest
from conftest import correct_choice, wait_for

from app.game import store


async def answer_correctly(client, room, *, offset: int = 0):
    """Answer the open question — correctly, or `offset` places away from it."""
    question = room.current
    await client.send(
        "answer",
        questionIndex=question.index,
        choice=(question.answer + offset) % len(question.options),
    )
    return question


# --------------------------------------------------------------------- lobby


async def test_a_new_room_gets_a_join_code(table):
    hub, _ = table

    room = hub.rooms.create("Sunday puppy jam", "p_a", "ilona")

    assert len(room.code) == 4
    assert room.code.isupper()
    # No characters that get misread when a code is typed off someone's screen.
    assert not set(room.code) & set("BIOSZ")
    assert room in hub.rooms.open_rooms()
    assert hub.rooms.by_code(room.code.lower()) is room, "codes are case-insensitive"


async def test_an_unnamed_room_is_named_after_its_host(table):
    hub, _ = table

    room = hub.rooms.create("", "p_a", "ilona")

    assert room.name == "ilona's room"


async def test_everyone_in_the_lobby_sees_the_same_state(lobby):
    _, clients, room = lobby

    await clients["p_c"].send("join", roomId=room.id)
    state = clients["p_c"].last("room_state")

    assert len(state["players"]) == 3
    assert state["hostId"] == "p_a", "whoever created the room hosts it"
    assert state["phase"] == "lobby"
    assert state["question"] is None, "the lobby must not leak the first question"


async def test_joining_twice_does_not_take_two_seats(lobby):
    hub, clients, room = lobby

    await clients["p_b"].send("join", code=room.code)

    assert len(room.members) == 3


async def test_joining_a_room_that_is_gone_reports_it(lobby):
    _, clients, _ = lobby

    await clients["p_a"].send("join", code="ZZZZ")

    assert "doesn't exist" in clients["p_a"].last("error")["message"]


@pytest.mark.parametrize("action,payload", [("start", {}), ("set_options", {"roundsTotal": 20})])
async def test_only_the_host_controls_the_game(lobby, action, payload):
    _, clients, room = lobby

    await clients["p_b"].send(action, **payload)

    assert clients["p_b"].last("error")["message"] == "Only the host can do that."
    assert room.phase == "lobby"
    assert room.rounds_total != 20


async def test_the_host_sets_the_rounds_and_the_clock(lobby):
    _, clients, room = lobby

    await clients["p_a"].send("set_options", roundsTotal=5, secondsPerQuestion=20)

    assert room.rounds_total == 5
    assert room.seconds_per_question == 20


async def test_nonsense_settings_are_refused(lobby):
    _, clients, room = lobby

    await clients["p_a"].send("set_options", roundsTotal=999)

    assert "between 5 and 20" in clients["p_a"].last("error")["message"]
    assert room.rounds_total != 999


# ------------------------------------------------------------------ answering


async def test_a_choice_stays_secret_until_the_reveal(in_play):
    _, clients, room = in_play

    await answer_correctly(clients["p_a"], room)
    state = clients["p_c"].last("room_state")
    locked = {p["playerId"]: p["answered"] for p in state["players"]}

    assert locked["p_a"] is True, "others can see that A has locked in"
    assert locked["p_b"] is False
    assert state["answerIndex"] is None, "the answer key is not out yet"
    assert all(p["lastCorrect"] is None for p in state["players"]), "nor is who got it right"


async def test_only_your_first_answer_counts(in_play):
    _, clients, room = in_play
    question = await answer_correctly(clients["p_a"], room)

    # Try to switch to a wrong answer after the fact.
    await clients["p_a"].send("answer", questionIndex=question.index, choice=(question.answer + 1) % 4)

    assert clients["p_a"].last("answer_rejected")["message"] == "You already locked in an answer."
    assert room.members["p_a"].answer == question.answer, "the original answer stands"


async def test_an_answer_to_the_wrong_question_is_refused(in_play):
    _, clients, room = in_play

    await clients["p_a"].send("answer", questionIndex=room.q_index + 5, choice=0)

    assert "already closed" in clients["p_a"].last("answer_rejected")["message"]
    assert room.members["p_a"].answer is None


async def test_an_option_that_does_not_exist_is_refused(in_play):
    _, clients, room = in_play

    await clients["p_a"].send("answer", questionIndex=room.q_index, choice=99)

    assert "isn't one of the options" in clients["p_a"].last("answer_rejected")["message"]


async def test_the_question_closes_early_once_everyone_has_answered(in_play):
    _, clients, room = in_play

    for client in clients.values():
        await answer_correctly(client, room)

    # 10s on the clock, but nobody should be made to wait for it.
    assert await wait_for(lambda: room.phase == "reveal", timeout=1.0)


async def test_answering_faster_scores_more(in_play):
    _, clients, room = in_play

    await answer_correctly(clients["p_a"], room)
    await asyncio.sleep(1.0)
    await answer_correctly(clients["p_b"], room)
    await answer_correctly(clients["p_c"], room)

    assert await wait_for(lambda: room.phase in ("reveal", "over"))
    scores = {p["playerId"]: p for p in clients["p_a"].last("question_end")["players"]}
    assert scores["p_a"]["lastAward"] > scores["p_b"]["lastAward"]


async def test_a_wrong_answer_scores_nothing_and_breaks_the_streak(in_play):
    _, clients, room = in_play

    await answer_correctly(clients["p_a"], room)
    await answer_correctly(clients["p_c"], room, offset=1)
    await answer_correctly(clients["p_b"], room)

    assert await wait_for(lambda: room.phase in ("reveal", "over"))
    end = clients["p_c"].last("question_end")
    scores = {p["playerId"]: p for p in end["players"]}

    assert scores["p_c"]["lastAward"] == 0
    assert scores["p_c"]["lastCorrect"] is False
    assert scores["p_c"]["streak"] == 0
    assert scores["p_a"]["lastAward"] > 0
    assert end["answerIndex"] == room.questions[end["questionNumber"] - 1].answer


async def test_a_streak_adds_a_bonus(in_play):
    _, clients, room = in_play
    awards = []

    for _ in range(3):
        assert await wait_for(lambda: room.phase == "question")
        for client in clients.values():
            await answer_correctly(client, room)
        assert await wait_for(lambda: room.phase in ("reveal", "over"))
        scores = {p["playerId"]: p for p in clients["p_a"].last("question_end")["players"]}
        awards.append(scores["p_a"]["lastAward"])
        assert await wait_for(lambda: room.phase != "reveal")

    assert awards == sorted(awards), f"each correct answer in a row should be worth more: {awards}"
    assert awards[-1] > awards[0]


# ------------------------------------------------------------- whole game


async def test_a_game_runs_to_a_podium_and_records_results(in_play):
    _, clients, room = in_play

    for round_no in range(5):
        assert await wait_for(lambda: room.phase == "question"), f"round {round_no} never opened"
        await answer_correctly(clients["p_a"], room)
        await answer_correctly(clients["p_b"], room, offset=1)
        await answer_correctly(clients["p_c"], room, offset=1)
        assert await wait_for(lambda: room.phase != "question")

    assert await wait_for(lambda: clients["p_a"].last("game_over") is not None)
    assert room.phase == "over"

    podium = clients["p_a"].last("game_over")["players"]
    assert podium[0]["playerId"] == "p_a", "the only player answering correctly should win"
    assert podium[0]["score"] > 0
    assert [p["score"] for p in podium[1:]] == [0, 0]

    board = {e["playerId"]: e for e in store.top(store.BOARD_MULTIPLAYER)}
    assert board["p_a"]["wins"] == 1
    assert board["p_b"]["wins"] == 0
    assert board["p_a"]["best"] == podium[0]["score"]
    assert board["p_a"]["gamesPlayed"] == 1


async def test_play_again_clears_the_scores_but_keeps_the_room(in_play):
    _, clients, room = in_play
    for _ in range(5):
        assert await wait_for(lambda: room.phase == "question")
        for client in clients.values():
            await answer_correctly(client, room)
        assert await wait_for(lambda: room.phase != "question")
    assert await wait_for(lambda: room.phase == "over")

    await clients["p_a"].send("again")

    assert room.phase == "lobby"
    assert len(room.members) == 3
    assert all(m.score == 0 for m in room.members.values())


async def test_you_cannot_play_again_mid_game(in_play):
    _, clients, room = in_play

    await clients["p_a"].send("again")

    assert "Finish the game first" in clients["p_a"].last("error")["message"]


# --------------------------------------------------------- coming and going


async def test_a_dropped_socket_keeps_your_seat_and_score(in_play):
    hub, clients, room = in_play
    await answer_correctly(clients["p_a"], room)
    assert await wait_for(lambda: room.members["p_a"].score > 0, timeout=12)
    score_before = room.members["p_a"].score

    await hub.on_disconnect("p_a")

    assert "p_a" in room.members, "a refresh must not cost you your seat"
    assert room.members["p_a"].connected is False
    assert room.members["p_a"].score == score_before

    await clients["p_a"].send("join", roomId=room.id)

    assert room.members["p_a"].connected is True
    assert room.members["p_a"].score == score_before


async def test_leaving_on_purpose_gives_up_the_seat(lobby):
    _, clients, room = lobby

    await clients["p_c"].send("leave")

    assert "p_c" not in room.members
    assert clients["p_a"].last("player_left")["playerId"] == "p_c"


async def test_the_host_role_is_handed_on_when_the_host_leaves(lobby):
    _, clients, room = lobby

    await clients["p_a"].send("leave")

    assert room.host_id == "p_b", "the longest-serving player takes over"
    assert clients["p_b"].last("room_state")["hostId"] == "p_b"


async def test_a_room_nobody_returns_to_is_closed(lobby, monkeypatch):
    hub, clients, room = lobby
    from app.game import rooms

    monkeypatch.setattr(rooms, "EMPTY_ROOM_GRACE", 0.05)

    for player_id in list(room.members):
        await hub.on_disconnect(player_id)

    assert await wait_for(lambda: hub.rooms.get(room.id) is None), "the empty room should be reaped"
    assert hub.rooms.by_code(room.code) is None, "and its code freed for reuse"


async def test_a_game_in_progress_does_not_accept_newcomers(in_play):
    hub, clients, room = in_play
    from conftest import FakeClient

    latecomer = FakeClient(hub, "p_late", "late")
    clients["p_late"] = latecomer
    await latecomer.send("join", roomId=room.id)

    assert "already in progress" in latecomer.last("error")["message"]
    assert "p_late" not in room.members


async def test_an_unknown_event_is_reported_not_ignored(lobby):
    _, clients, _ = lobby

    await clients["p_a"].send("do_a_barrel_roll")

    assert "Unknown game event" in clients["p_a"].last("error")["message"]
