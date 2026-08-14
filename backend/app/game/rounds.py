"""Question building, shared by both game modes.

One question = one human face plus N dog photos, exactly one of which is the
right answer. The answer index lives here on the server and is only ever sent to
a client *after* the question is closed, so a player reading network traffic
still has to guess.

Solo uses two options and asks for questions one at a time; multiplayer uses four
and builds the whole game upfront.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import content


@dataclass
class Question:
    """A built question. `answer` never leaves the server before the reveal."""

    index: int
    item_id: str
    human_seed: str
    human_url: str | None
    options: list[int]  # dog indices, already shuffled
    answer: int  # position of the correct dog within `options`

    def payload(self) -> dict:
        """The client-safe shape — everything except the answer."""
        return {
            "index": self.index,
            "itemId": self.item_id,
            "humanSeed": self.human_seed,
            "humanUrl": self.human_url,
            "options": self.options,
        }


def build_question(
    index: int,
    rng: random.Random,
    options_per: int = 4,
    used_item_ids: set[str] | None = None,
) -> Question | None:
    """Build one question, avoiding humans already used in this game/run."""
    items = content.pick_items(1, rng, exclude=used_item_ids)
    if not items:
        return None
    item = items[0]

    decoys = content.pick_decoy_dogs(options_per - 1, rng, exclude={item.dog_index})
    if len(decoys) < options_per - 1:
        return None

    options = [item.dog_index, *decoys]
    rng.shuffle(options)
    return Question(
        index=index,
        item_id=item.id,
        human_seed=item.human_seed,
        human_url=item.human_url,
        options=options,
        answer=options.index(item.dog_index),
    )


def build_questions(count: int, rng: random.Random, options_per: int = 4) -> list[Question]:
    """Build a whole game's worth of questions with no repeated humans."""
    questions: list[Question] = []
    used: set[str] = set()
    for i in range(count):
        question = build_question(i, rng, options_per=options_per, used_item_ids=used)
        if question is None:
            break
        used.add(question.item_id)
        questions.append(question)
    return questions
