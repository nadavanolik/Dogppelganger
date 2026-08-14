"""The Mix & Match board: dealing and marking.

No event loop and no room here — that separation is the whole reason
``board.py`` holds no clock and no transport.
"""
import random

import pytest

from app.game import board as boards
from app.game.board import DOGS_PER_BOARD, HUMANS_PER_BOARD


@pytest.fixture
def dealt():
    return boards.build_board(random.Random(1234))


def test_a_board_has_four_of_each(dealt):
    assert len(dealt.humans) == HUMANS_PER_BOARD
    assert len(dealt.dogs) == DOGS_PER_BOARD


def test_every_dog_belongs_to_someone_on_the_board(dealt):
    """No decoys: the four dogs are exactly the four humans' dogs."""
    assert sorted(dealt.dogs) == sorted(item.dog_index for item in dealt.humans)


def test_the_answer_is_a_one_to_one_mapping(dealt):
    assert sorted(dealt.answer) == list(range(HUMANS_PER_BOARD))
    assert sorted(dealt.answer.values()) == list(range(DOGS_PER_BOARD))


def test_humans_are_distinct(dealt):
    assert len({item.id for item in dealt.humans}) == HUMANS_PER_BOARD


def test_the_payload_hides_the_answer(dealt):
    payload = dealt.payload()
    assert set(payload) == {"humans", "dogs"}
    flat = repr(payload)
    assert "answer" not in flat
    # Slots are array positions, which is what a claim refers to.
    assert [h["slot"] for h in payload["humans"]] == list(range(HUMANS_PER_BOARD))
    assert [d["slot"] for d in payload["dogs"]] == list(range(DOGS_PER_BOARD))


def test_the_dog_order_is_independent_of_the_human_order(dealt):
    """If slot i always paired with slot i, the game would be trivial. Over many
    boards the identity mapping should be rare, not the rule."""
    identities = 0
    for seed in range(60):
        board = boards.build_board(random.Random(seed))
        if all(board.answer[i] == i for i in range(HUMANS_PER_BOARD)):
            identities += 1
    assert identities <= 3


def test_grading_a_perfect_board(dealt):
    marks = boards.grade(dealt, dict(dealt.answer))
    assert all(marks.values())
    assert boards.correct_count(dealt, dict(dealt.answer)) == HUMANS_PER_BOARD
    assert boards.is_perfect(dealt, dict(dealt.answer))


def test_grading_a_partial_board(dealt):
    """Humans left unpaired aren't wrong — they simply don't score."""
    pairs = {0: dealt.answer[0]}
    assert boards.correct_count(dealt, pairs) == 1
    assert not boards.is_perfect(dealt, pairs)


def test_a_full_board_is_never_wrong_on_exactly_one(dealt):
    """The fact the solo lives rule is built on.

    With four humans on four distinct dogs, the smallest possible mistake is a
    swap, which is wrong twice. So the wrong count is 0, 2, 3 or 4 — never 1.
    """
    seen = set()
    for permutation in _permutations(range(DOGS_PER_BOARD)):
        pairs = dict(enumerate(permutation))
        seen.add(HUMANS_PER_BOARD - boards.correct_count(dealt, pairs))
    assert seen == {0, 2, 3, 4}


def test_a_swap_scores_two(dealt):
    pairs = dict(dealt.answer)
    pairs[0], pairs[1] = pairs[1], pairs[0]
    assert boards.correct_count(dealt, pairs) == HUMANS_PER_BOARD - 2
    assert not boards.is_perfect(dealt, pairs)


def test_the_answer_payload_is_json_safe(dealt):
    payload = dealt.answer_payload()
    assert all(isinstance(key, str) for key in payload)
    assert {int(k): v for k, v in payload.items()} == dealt.answer


def _permutations(values):
    values = list(values)
    if len(values) <= 1:
        yield values
        return
    for i, value in enumerate(values):
        for rest in _permutations(values[:i] + values[i + 1 :]):
            yield [value, *rest]
