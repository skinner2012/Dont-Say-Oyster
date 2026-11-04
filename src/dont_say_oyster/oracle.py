"""The Oracle's name checks on one card: the guess check [R20], [R5], the Describer check [R21],
the question check [R17], and the memory check (Cross-game memory definition, Check rule), on
the matching helpers [R22]. Pure functions that only report;
send-backs, violations, rounds, and counters are the nodes'. Matched names are given as written
on the card or in the corpus, in list order.

A list item that normalizes to empty matches every text (deferred, author, 2026-10-19); the checks
do not skip such items but rely on the corpus having none, so a bad item shows in every check
instead of being dropped silently."""

from collections.abc import Sequence
from dataclasses import dataclass

from dont_say_oyster.cards import Card
from dont_say_oyster.corpus import CorpusEntry
from dont_say_oyster.matching import (
    chinese_contains,
    chinese_equals,
    english_contains,
    has_chinese_characters,
)
from dont_say_oyster.memory import Role


@dataclass(frozen=True)
class GuessCheck:
    """`matched`: the name the guess equals [R20], the first in the card's list order (official
    name, then aliases as listed) when two names of the card are equal after normalization, or
    None; `in_chinese`: whether the guess has a Chinese character [R5]. A guess is correct when
    both hold."""

    matched: str | None
    in_chinese: bool

    @property
    def correct(self) -> bool:
        return self.in_chinese and self.matched is not None


@dataclass(frozen=True)
class DescriberCheck:
    """What the text contains [R21]: `names` (official name and aliases, by the Chinese rule),
    `english_names` and `forbidden_words` (by the English rule) [R22]."""

    names: tuple[str, ...]
    english_names: tuple[str, ...]
    forbidden_words: tuple[str, ...]

    @property
    def violation(self) -> bool:
        return bool(self.names or self.english_names or self.forbidden_words)


@dataclass(frozen=True)
class QuestionCheck:
    """Why a question is invalid [R17]: `has_chinese`; `english_names`, the card's English names
    it contains; `distractor_names`, (distractor official name, its English name) pairs it
    contains, the English names looked up in the corpus [R22]."""

    has_chinese: bool
    english_names: tuple[str, ...]
    distractor_names: tuple[tuple[str, str], ...]

    @property
    def invalid(self) -> bool:
        return self.has_chinese or bool(self.english_names or self.distractor_names)


@dataclass(frozen=True)
class MemoryCheck:
    """What one memory text contains (Cross-game memory definition, Check rule): `has_chinese`
    [R6]; for the Guesser only, `names`, the card's official name and aliases it contains by the
    Chinese rule, and `english_names`, the card's English names it contains by the English rule,
    plurals included [R22]. Both are empty for the Describer, whose check is Chinese characters
    alone, since the Write rule allows its entry card information."""

    has_chinese: bool
    names: tuple[str, ...]
    english_names: tuple[str, ...]

    @property
    def failed(self) -> bool:
        return self.has_chinese or bool(self.names or self.english_names)


def check_guess(guess: str, card: Card) -> GuessCheck:
    """The guess against the card's official name and aliases, by equals [R20], [R22]."""
    matched = chinese_equals(guess, (card.official_name, *card.aliases))
    return GuessCheck(
        matched=matched[0] if matched else None,
        in_chinese=has_chinese_characters(guess),
    )


def check_describer(text: str, card: Card) -> DescriberCheck:
    """A description or answer against the card's names, English names, and forbidden words
    [R21], [R22]."""
    return DescriberCheck(
        names=tuple(chinese_contains(text, (card.official_name, *card.aliases))),
        english_names=tuple(english_contains(text, card.english_names)),
        forbidden_words=tuple(english_contains(text, card.forbidden_words)),
    )


def check_question(question: str, card: Card, corpus: Sequence[CorpusEntry]) -> QuestionCheck:
    """A question against Chinese characters and the English names of the card and of its
    distractors, found in `corpus` by official name [R17], [R22]. Raises ValueError when a
    distractor is not an official name in `corpus`."""
    by_name = {entry.official_name: entry for entry in corpus}
    missing = [name for name in card.distractors if name not in by_name]
    if missing:
        raise ValueError(f"distractors not in the corpus: {', '.join(missing)}")
    return QuestionCheck(
        has_chinese=has_chinese_characters(question),
        english_names=tuple(english_contains(question, card.english_names)),
        distractor_names=tuple(
            (name, english)
            for name in card.distractors
            for english in english_contains(question, by_name[name].english_names)
        ),
    )


def check_memory(text: str, card: Card, role: Role) -> MemoryCheck:
    """One memory text (an entry or a rolling summary) of `role` against Chinese characters
    [R6] and, for the Guesser, the card's official name, aliases, and English names (Cross-game
    memory definition, Check rule) [R22]. Nothing else is in the set: not the forbidden words,
    which the Guesser never sees, and not the distractors."""
    if role == "describer":
        return MemoryCheck(has_chinese=has_chinese_characters(text), names=(), english_names=())
    return MemoryCheck(
        has_chinese=has_chinese_characters(text),
        names=tuple(chinese_contains(text, (card.official_name, *card.aliases))),
        english_names=tuple(english_contains(text, card.english_names)),
    )
