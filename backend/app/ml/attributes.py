"""The shared vocabulary both species get scored against.

This is the bridge that makes cross-species matching possible at all. CLIP's
raw image embeddings are dominated by *what kind of thing* is in the picture:
every dog lands in one tight cluster, every human in another, and the little
variation left over is mostly background and lighting. Scoring both against the
same words instead puts a person and a dog in one small, species-neutral space
— and, as a side effect, gives a real answer to "why this dog?" rather than a
bare percentage.

**Choosing attributes.** Each has to be gradable on a human face *and* a dog
face. "Fluffy" reads on a person's hair and a dog's coat alike; "wet nose"
would only ever be true of one side and so carries no matching signal, only a
constant offset. Prompts are written out per attribute instead of slotted into
a template, because forcing every trait through one sentence shape produces
English that CLIP has never seen ("a photo of a big ears face").

Several prompts per attribute are averaged — standard CLIP prompt ensembling,
which is noticeably more stable than any single wording.
"""
from __future__ import annotations

from dataclasses import dataclass

# Bump when the vocabulary or its prompts change: it is stored alongside every
# attribute vector, so a mismatch between corpus and calibration is detectable
# rather than silently comparing incompatible spaces.
ATTRIBUTE_SET = "v1"


@dataclass(frozen=True)
class Attribute:
    label: str  # shown to the user as a shared trait
    prompts: tuple[str, ...]  # averaged into one text embedding


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("fluffy", ("a photo of a very fluffy, furry face", "a close-up of a fluffy hairy face")),
    Attribute("sleek", ("a photo of a sleek, smooth, short-haired face", "a close-up of a smooth glossy face")),
    Attribute("shaggy hair", ("a photo of a face with long shaggy messy hair", "a close-up of an unkempt shaggy face")),
    Attribute("neatly groomed", ("a photo of a neatly groomed, tidy face", "a close-up of a well-groomed face")),
    Attribute("sleepy eyes", ("a photo of a sleepy face with half-closed eyes", "a close-up of a drowsy tired face")),
    Attribute("wide eyed", ("a photo of a wide-eyed alert face", "a close-up of a face with big open eyes")),
    Attribute("long face", ("a photo of a long narrow face", "a close-up of a face with a long snout or long jaw")),
    Attribute("round face", ("a photo of a round chubby face", "a close-up of a wide flat round face")),
    Attribute("grumpy", ("a photo of a grumpy frowning face", "a close-up of a disapproving sulky face")),
    Attribute("goofy grin", ("a photo of a goofy happy grinning face", "a close-up of a silly cheerful face")),
    Attribute("serious", ("a photo of a serious stern dignified face", "a close-up of a solemn formal face")),
    Attribute("big ears", ("a photo of a face with big prominent ears", "a close-up of a face with large sticking-out ears")),
    Attribute("golden colouring", ("a photo of a golden blonde face", "a close-up of a light golden-haired face")),
    Attribute("dark colouring", ("a photo of a black-haired dark face", "a close-up of a very dark coloured face")),
    Attribute("ginger colouring", ("a photo of a ginger red-haired face", "a close-up of a reddish auburn face")),
    Attribute("greying", ("a photo of a grey and white haired older face", "a close-up of a greying elderly face")),
)

LABELS: tuple[str, ...] = tuple(a.label for a in ATTRIBUTES)
DIM = len(ATTRIBUTES)


def prompts() -> list[list[str]]:
    """Prompts grouped per attribute, in ATTRIBUTES order."""
    return [list(a.prompts) for a in ATTRIBUTES]
