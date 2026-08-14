"""Solo Mix & Match: three lives, no clock, board after board."""
import pytest
from conftest import perfect_pairs

from app.game import solo_match, store


def wrong_by_a_swap(board: dict) -> dict[int, int]:
    """The smallest possible mistake: two humans' dogs exchanged."""
    pairs = perfect_pairs(board)
    pairs[0], pairs[1] = pairs[1], pairs[0]
    return pairs


def test_a_run_starts_with_three_lives_and_a_board():
    run = solo_match.start_run("p1", "nadav")
    assert run["lives"] == 3
    assert run["score"] == 0
    assert run["over"] is False
    assert len(run["board"]["humans"]) == 4
    assert len(run["board"]["dogs"]) == 4


def test_the_board_never_carries_its_answer():
    run = solo_match.start_run("p1", "nadav")
    assert "answer" not in repr(run["board"])


def test_a_perfect_board_costs_nothing_and_scores_four():
    run = solo_match.start_run("p1", "nadav")
    result = solo_match.submit(run["runToken"], perfect_pairs(run["board"]))

    assert result["wasPerfect"] is True
    assert result["roundCorrect"] == 4
    assert result["score"] == 4
    assert result["lives"] == 3
    assert result["streak"] == 1
    assert result["over"] is False
    assert result["board"] is not None  # the next one is already dealt


def test_an_imperfect_board_costs_exactly_one_life():
    """Two wrong is the minimum, so charging per pair would cost two lives."""
    run = solo_match.start_run("p1", "nadav")
    result = solo_match.submit(run["runToken"], wrong_by_a_swap(run["board"]))

    assert result["roundCorrect"] == 2
    assert result["wasPerfect"] is False
    assert result["lives"] == 2
    assert result["streak"] == 0


def test_a_completely_wrong_board_also_costs_only_one_life():
    run = solo_match.start_run("p1", "nadav")
    right = perfect_pairs(run["board"])
    rotated = {human: (right[human] + 1) % 4 for human in right}
    result = solo_match.submit(run["runToken"], rotated)

    assert result["roundCorrect"] == 0
    assert result["lives"] == 2


def test_a_partial_board_is_allowed_and_scores_what_it_got():
    run = solo_match.start_run("p1", "nadav")
    right = perfect_pairs(run["board"])
    result = solo_match.submit(run["runToken"], {0: right[0]})

    assert result["roundCorrect"] == 1
    assert result["wasPerfect"] is False  # incomplete is not perfect
    assert result["lives"] == 2


def test_three_imperfect_boards_end_the_run():
    run = solo_match.start_run("p1", "nadav")
    result = run
    for expected_lives in (2, 1, 0):
        result = solo_match.submit(result["runToken"], wrong_by_a_swap(result["board"]))
        if expected_lives:
            assert result["lives"] == expected_lives

    assert result["over"] is True
    assert result["board"] is None
    assert result["score"] == 6  # two right on each of three boards


def test_scores_accumulate_across_boards():
    run = solo_match.start_run("p1", "nadav")
    result = run
    for _ in range(3):
        result = solo_match.submit(result["runToken"], perfect_pairs(result["board"]))
    assert result["score"] == 12
    assert result["longestStreak"] == 3
    assert result["lives"] == 3


def test_each_board_is_a_fresh_one():
    run = solo_match.start_run("p1", "nadav")
    first = {h["humanSeed"] for h in run["board"]["humans"]}
    result = solo_match.submit(run["runToken"], perfect_pairs(run["board"]))
    second = {h["humanSeed"] for h in result["board"]["humans"]}
    assert first != second


def test_the_answer_comes_back_once_the_board_is_closed():
    run = solo_match.start_run("p1", "nadav")
    right = perfect_pairs(run["board"])
    result = solo_match.submit(run["runToken"], right)

    assert {int(k): v for k, v in result["boardAnswer"].items()} == right
    assert result["marks"] == {str(h): True for h in right}


def test_two_humans_cannot_share_a_dog():
    run = solo_match.start_run("p1", "nadav")
    with pytest.raises(ValueError):
        solo_match.submit(run["runToken"], {0: 1, 2: 1})


def test_pairings_off_the_board_are_refused():
    run = solo_match.start_run("p1", "nadav")
    with pytest.raises(ValueError):
        solo_match.submit(run["runToken"], {9: 0})
    with pytest.raises(ValueError):
        solo_match.submit(run["runToken"], {0: 9})


def test_an_unknown_token_is_rejected():
    with pytest.raises(solo_match.UnknownRun):
        solo_match.submit("not-a-real-token", {})


def test_a_finished_token_stops_working():
    run = solo_match.start_run("p1", "nadav")
    result = run
    for _ in range(3):
        result = solo_match.submit(result["runToken"], wrong_by_a_swap(result["board"]))
    with pytest.raises(solo_match.UnknownRun):
        solo_match.submit(run["runToken"], {})


def test_a_finished_run_lands_on_its_own_leaderboard():
    run = solo_match.start_run("p1", "nadav")
    result = run
    for _ in range(3):
        result = solo_match.submit(result["runToken"], wrong_by_a_swap(result["board"]))

    assert result["rank"] == 1
    assert [e["playerId"] for e in result["leaderboard"]] == ["p1"]
    assert store.top(store.BOARD_SOLO_MATCH)[0]["best"] == 6
    # Streak Survival counts answers, not points — nothing leaks across.
    assert store.top(store.BOARD_SOLO) == []


def test_an_unfinished_run_is_not_on_the_board():
    run = solo_match.start_run("p1", "nadav")
    solo_match.submit(run["runToken"], perfect_pairs(run["board"]))
    assert store.top(store.BOARD_SOLO_MATCH) == []
