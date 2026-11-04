"""Oracle checks on the committed card 烤蚵仔 and the committed corpus."""

from dataclasses import replace

import pytest

from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, Card, card_id, load_cards
from dont_say_oyster.corpus import CorpusEntry, load_corpus
from dont_say_oyster.oracle import (
    MemoryCheck,
    check_describer,
    check_guess,
    check_memory,
    check_question,
)

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"


@pytest.fixture(scope="module")
def corpus() -> list[CorpusEntry]:
    return load_corpus(CORPUS_PATH)


@pytest.fixture(scope="module")
def card(corpus: list[CorpusEntry]) -> Card:
    (found,) = [c for c in load_cards(CARDS_PATH, corpus) if c.card_id == "card-5ed17f8f"]
    assert found.official_name == "烤蚵仔"
    return found


# Guess [R20], [R5]


def test_guess_official_name_is_right(card: Card) -> None:
    result = check_guess("烤蚵仔", card)
    assert result.correct
    assert result.matched == "烤蚵仔"
    assert result.in_chinese


def test_guess_simplified_alias_is_right_as_the_alias(card: Card) -> None:
    result = check_guess("烤牡蛎", card)
    assert result.correct
    assert result.matched == "烤牡蠣"


def test_guess_reports_the_first_match_in_card_order(card: Card) -> None:
    """Two aliases equal only after normalization both equal the guess; the check names the
    first in the card's list order."""
    twin = replace(card, aliases=("蚵煎", "蚵 煎"))
    result = check_guess("蚵 煎", twin)
    assert result.correct
    assert result.matched == "蚵煎"


@pytest.mark.parametrize("guess", ["烤蚵仔好吃", "蚵仔煎"])
def test_guess_that_equals_no_name_is_wrong(card: Card, guess: str) -> None:
    result = check_guess(guess, card)
    assert not result.correct
    assert result.matched is None
    assert result.in_chinese


def test_guess_not_in_chinese_is_wrong(card: Card) -> None:
    result = check_guess("kao o-a", card)
    assert not result.correct
    assert not result.in_chinese


def test_guess_in_chinese_but_wrong(card: Card) -> None:
    result = check_guess("雪Q餅", card)
    assert not result.correct
    assert result.in_chinese


def test_guess_with_an_english_tail_is_wrong(corpus: list[CorpusEntry]) -> None:
    """Q20: the decorated guess from the live tool-calling check, on a card made from its own corpus
    entry, is in Chinese but equals no name after normalization, so it is wrong under [R20] as
    written."""
    (entry,) = [e for e in corpus if e.official_name == "黑糖珍珠鮮奶"]
    own = Card(
        card_id=card_id(entry.official_name),
        official_name=entry.official_name,
        aliases=entry.aliases,
        english_names=entry.english_names,
        forbidden_words=entry.forbidden_words,
        attributes=entry.attributes,
        distractors=(),
    )
    result = check_guess("黑糖珍珠鮮奶 (Brown Sugar Boba Milk)", own)
    assert result.in_chinese
    assert not result.correct
    assert result.matched is None
    assert check_guess("黑糖珍珠鮮奶", own).correct


# Describer [R21]


def test_describer_english_name_with_case_changed(card: Card) -> None:
    result = check_describer("Grilled Oyster", card)
    assert result.english_names == ("Grilled oyster",)
    assert result.violation


def test_describer_forbidden_word_in_plural(card: Card) -> None:
    result = check_describer("oysters", card)
    assert result.forbidden_words == ("oyster",)
    assert result.english_names == ()
    assert result.violation


def test_describer_forbidden_word(card: Card) -> None:
    result = check_describer("charcoal", card)
    assert result.forbidden_words == ("charcoal",)
    assert result.violation


def test_describer_alias(card: Card) -> None:
    result = check_describer("烤生蠔", card)
    assert result.names == ("烤生蠔",)
    assert result.english_names == ()
    assert result.forbidden_words == ()
    assert result.violation


def test_describer_clean_text_passes(card: Card) -> None:
    result = check_describer("drawn on the street", card)
    assert result.names == ()
    assert result.english_names == ()
    assert result.forbidden_words == ()
    assert not result.violation


# Question [R17]


def test_question_with_chinese_is_invalid(card: Card, corpus: list[CorpusEntry]) -> None:
    result = check_question("Does it have 蚵?", card, corpus)
    assert result.has_chinese
    assert result.invalid


def test_question_with_the_cards_english_name_in_plural(
    card: Card, corpus: list[CorpusEntry]
) -> None:
    result = check_question("Is it grilled oysters?", card, corpus)
    assert result.english_names == ("Grilled oyster",)
    assert not result.has_chinese
    assert result.invalid


def test_question_with_a_distractors_english_name(card: Card, corpus: list[CorpusEntry]) -> None:
    result = check_question("Is it like an oyster omelet?", card, corpus)
    assert result.distractor_names == (("蚵仔煎", "Oyster Omelet"),)
    assert result.english_names == ()
    assert result.invalid


@pytest.mark.parametrize(
    "question", ["Is it o-a-tsian?", "is it o a tsian", "Is it o‐a‐tsian?"]
)
def test_question_with_a_distractors_romanization(
    card: Card, corpus: list[CorpusEntry], question: str
) -> None:
    result = check_question(question, card, corpus)
    assert result.distractor_names == (("蚵仔煎", "o-a-tsian"),)
    assert result.invalid


@pytest.mark.parametrize("question", ["Does it have oysters?", "Is it sold at night markets?"])
def test_valid_question(card: Card, corpus: list[CorpusEntry], question: str) -> None:
    result = check_question(question, card, corpus)
    assert not result.has_chinese
    assert result.english_names == ()
    assert result.distractor_names == ()
    assert not result.invalid


def test_question_with_a_non_distractors_english_name_is_valid(
    card: Card, corpus: list[CorpusEntry]
) -> None:
    """Only the card's distractors are looked up, by official name [R17]; another corpus entry's
    English name leaves the question valid."""
    (entry,) = [e for e in corpus if e.official_name == "豬血糕"]
    assert "Pig's blood cake" in entry.english_names
    assert entry.official_name not in card.distractors
    result = check_question("Is it a pig's blood cake?", card, corpus)
    assert result.distractor_names == ()
    assert not result.invalid


def test_question_distractor_missing_from_corpus(card: Card, corpus: list[CorpusEntry]) -> None:
    others = [e for e in corpus if e.official_name != "蚵仔煎"]
    with pytest.raises(ValueError, match="蚵仔煎"):
        check_question("Is it sold at night markets?", card, others)


# Memory (Cross-game memory definition, Check rule), [R6]


def test_memory_describer_reports_chinese_characters_only(card: Card) -> None:
    result = check_memory("The Guesser confused it with 蚵仔煎", card, "describer")
    assert result == MemoryCheck(has_chinese=True, names=(), english_names=())
    assert result.failed


def test_memory_describer_naming_the_snack_in_english_passes(card: Card) -> None:
    # The Write rule allows the Describer's entry card information: English names and forbidden
    # words are not in its check.
    result = check_memory("Grilled oysters confused the Guesser; charcoal was the hint", card,
                          "describer")
    assert result == MemoryCheck(has_chinese=False, names=(), english_names=())
    assert not result.failed


def test_memory_describer_official_name_reports_chinese_only(card: Card) -> None:
    result = check_memory("烤蚵仔", card, "describer")
    assert result == MemoryCheck(has_chinese=True, names=(), english_names=())


def test_memory_guesser_reports_the_official_name(card: Card) -> None:
    result = check_memory("I should have guessed 烤蚵仔 earlier", card, "guesser")
    assert result.names == ("烤蚵仔",)
    assert result.has_chinese
    assert result.failed


def test_memory_guesser_reports_a_simplified_alias(card: Card) -> None:
    result = check_memory("烤生蚝", card, "guesser")
    assert result.names == ("烤生蠔",)


def test_memory_guesser_reports_an_english_name_in_plural(card: Card) -> None:
    result = check_memory("Searching for grilled oysters narrowed it", card, "guesser")
    assert result == MemoryCheck(has_chinese=False, names=(), english_names=("Grilled oyster",))
    assert result.failed


def test_memory_guesser_clean_english_entry_passes(card: Card) -> None:
    # Forbidden words are not in the Guesser's set: it never sees them.
    result = check_memory("Filter by cooking method first; charcoal is a common hint", card,
                          "guesser")
    assert result == MemoryCheck(has_chinese=False, names=(), english_names=())
    assert not result.failed


def test_memory_guesser_reports_every_reason_that_applies(card: Card) -> None:
    result = check_memory("烤蚵仔, the grilled oysters", card, "guesser")
    assert result == MemoryCheck(has_chinese=True, names=("烤蚵仔",),
                                 english_names=("Grilled oyster",))
