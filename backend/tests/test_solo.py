"""Single-player Streak Survival: three lives, no clock, score is how far you got."""
import pytest
from conftest import correct_choice

from app.game import solo, store


def play_correctly(token: str, state: dict, times: int) -> dict:
    for _ in range(times):
        state = solo.answer(token, correct_choice(state["question"]))
    return state


def test_a_new_run_serves_a_question_and_no_clock():
    run = solo.start_run("p1", "nadav")

    assert run["lives"] == 3
    assert run["score"] == 0
    assert run["question"] is not None
    assert len(run["question"]["options"]) == 2, "solo is a straight A-or-B call"
    # There is deliberately no timer in this mode, so nothing time-shaped should
    # appear in the payload for a client to render.
    assert "endsAt" not in run and "duration" not in run


def test_the_answer_key_never_ships_with_the_question():
    run = solo.start_run("p1", "nadav")

    assert "answer" not in run["question"]
    assert "answerIndex" not in run


def test_correct_answers_score_and_build_a_streak():
    run = solo.start_run("p1", "nadav")
    state = play_correctly(run["runToken"], run, 5)

    assert state["wasCorrect"] is True
    assert state["score"] == 5
    assert state["streak"] == 5
    assert state["longestStreak"] == 5
    assert state["lives"] == 3, "being right costs nothing"


def test_a_wrong_answer_costs_a_life_and_resets_the_streak():
    run = solo.start_run("p1", "nadav")
    state = play_correctly(run["runToken"], run, 3)
    assert state["streak"] == 3

    state = solo.answer(run["runToken"], 1 - correct_choice(state["question"]))

    assert state["wasCorrect"] is False
    assert state["lives"] == 2
    assert state["streak"] == 0
    assert state["longestStreak"] == 3, "the best streak still stands"
    assert state["score"] == 3, "you keep what you already got right"
    assert state["question"] is not None, "the run continues"


def test_the_answer_is_revealed_once_the_question_is_closed():
    run = solo.start_run("p1", "nadav")
    expected = correct_choice(run["question"])

    state = solo.answer(run["runToken"], expected)

    assert state["answerIndex"] == expected


def test_the_run_ends_at_zero_lives():
    run = solo.start_run("p1", "nadav")
    token = run["runToken"]
    state = play_correctly(token, run, 2)

    for expected_lives in (2, 1, 0):
        state = solo.answer(token, 1 - correct_choice(state["question"]))
        assert state["lives"] == expected_lives

    assert state["over"] is True
    assert state["question"] is None, "no more questions after game over"
    assert state["score"] == 2
    assert "leaderboard" in state and state["rank"] == 1


@pytest.mark.parametrize(
    "token_for",
    [
        pytest.param(lambda token: token, id="a finished run"),
        pytest.param(lambda _: "not-a-real-token", id="a token that never existed"),
    ],
)
def test_unplayable_runs_are_rejected(token_for):
    run = solo.start_run("p1", "nadav")
    token = run["runToken"]
    state = run
    for _ in range(3):  # burn all three lives
        state = solo.answer(token, 1 - correct_choice(state["question"]))

    with pytest.raises(solo.UnknownRun):
        solo.answer(token_for(token), 0)


def test_a_finished_run_lands_on_the_leaderboard():
    run = solo.start_run("p1", "nadav")
    token = run["runToken"]
    state = play_correctly(token, run, 4)
    for _ in range(3):
        state = solo.answer(token, 1 - correct_choice(state["question"]))

    entry = next(e for e in store.top(store.BOARD_SOLO) if e["playerId"] == "p1")

    assert entry["best"] == 4
    assert entry["longestStreak"] == 4
    assert entry["gamesPlayed"] == 1
    assert entry["name"] == "nadav"


def test_the_leaderboard_keeps_your_best_not_your_latest():
    first = solo.start_run("p1", "nadav")
    state = play_correctly(first["runToken"], first, 6)
    for _ in range(3):
        state = solo.answer(first["runToken"], 1 - correct_choice(state["question"]))

    second = solo.start_run("p1", "nadav")
    state = second
    for _ in range(3):  # a disastrous second run
        state = solo.answer(second["runToken"], 1 - correct_choice(state["question"]))

    entry = next(e for e in store.top(store.BOARD_SOLO) if e["playerId"] == "p1")

    assert entry["best"] == 6, "a bad run must not wipe out a good one"
    assert entry["gamesPlayed"] == 2
