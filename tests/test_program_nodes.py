"""State and the program nodes A, G, and F on the committed card 烤蚵仔 (T8 Acceptance)."""

import json
import types
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints, is_typeddict

import pytest
from langgraph.channels import LastValue
from langgraph.graph import StateGraph

from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, Card, load_cards
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.program_nodes import node_a, node_f, node_g, route_after_f
from dont_say_oyster.state import PROGRAM_ONLY, State, card_from_state, winner

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"
CARD_ID = "card-5ed17f8f"


@pytest.fixture(scope="module")
def cards() -> list[Card]:
    return load_cards(CARDS_PATH, load_corpus(CORPUS_PATH))


@pytest.fixture(scope="module")
def card(cards: list[Card]) -> Card:
    (found,) = [c for c in cards if c.card_id == CARD_ID]
    assert found.official_name == "烤蚵仔"
    return found


@pytest.fixture
def start(cards: list[Card]) -> State:
    return node_a(CARD_ID, cards)


def _conforms(value: Any, hint: Any) -> bool:
    """Whether `value` has the type `hint`, recursing into lists, dicts, and TypedDicts."""
    origin = get_origin(hint)
    if hint is Any:
        return True
    if hint is type(None):
        return value is None
    if origin in (Union, types.UnionType):
        return any(_conforms(value, arm) for arm in get_args(hint))
    if origin is Literal:
        return value in get_args(hint)
    if origin is list:
        (item,) = get_args(hint)
        return isinstance(value, list) and all(_conforms(v, item) for v in value)
    if origin is dict:
        key, item = get_args(hint)
        return isinstance(value, dict) and all(
            _conforms(k, key) and _conforms(v, item) for k, v in value.items()
        )
    if is_typeddict(hint):
        fields = get_type_hints(hint)
        return (
            isinstance(value, dict)
            and value.keys() == fields.keys()
            and all(_conforms(value[k], t) for k, t in fields.items())
        )
    if hint is float:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if hint is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, hint)


def _guess(state: State, text: str, round_: int) -> State:
    """`state` in round `round_` with the Guesser's latest output the guess `text`."""
    return {
        **state,
        "round": round_,
        "guesser_output": {
            "kind": "guess",
            "text": text,
            "confidence": 0.8,
            "latency": 1.0,
            "input_tokens": 10,
            "output_tokens": 5,
            "attempt": 1,
        },
    }


# A


def test_a_gives_every_row_with_its_type(start: State) -> None:
    hints = get_type_hints(State)
    assert start.keys() == hints.keys()
    for field, hint in hints.items():
        assert _conforms(start[field], hint), field  # type: ignore[literal-required]


def test_a_card_rows_equal_the_card(start: State, card: Card) -> None:
    assert card_from_state(start) == card
    assert start["names"][0] == "烤蚵仔"


def test_a_starts_with_no_result_and_zero_counters(start: State) -> None:
    assert start["result"] is None
    assert start["violation"] is None
    assert start["matched_name"] is None
    assert start["owes"] == "description"
    assert not start["guess_only"]
    for counter in (
        "round", "rejects", "lookup_count", "questions", "forced_passes",
        "describer_send_backs", "invalid_questions", "reason_reasks",
    ):
        assert start[counter] == 0, counter


def test_a_state_is_json(start: State) -> None:
    assert json.loads(json.dumps(start, ensure_ascii=False)) == start


def test_langgraph_takes_state_with_one_plain_channel_per_field() -> None:
    """No field has a reducer: a node's returned value replaces the field's value."""
    channels = StateGraph(State).channels
    assert channels.keys() == get_type_hints(State).keys()
    assert all(type(c) is LastValue for c in channels.values())


def test_program_only_fields_are_state_fields() -> None:
    assert PROGRAM_ONLY <= get_type_hints(State).keys()
    assert {"violation", "matched_name", "guess_only", "owes"} <= PROGRAM_ONLY
    assert not {"result", "round", "rejects", "lookup_count", "card_id"} & PROGRAM_ONLY


def test_a_unknown_card_id_raises_naming_it(cards: list[Card]) -> None:
    with pytest.raises(KeyError, match="card-00000000"):
        node_a("card-00000000", cards)


# G


def test_g_from_round_0_gives_round_1_and_zeroes_round_counters(start: State) -> None:
    state: State = {**start, "rejects": 2, "lookup_count": 4}
    after = node_g(state)
    assert after["round"] == 1
    assert after["rejects"] == 0
    assert after["lookup_count"] == 0


def test_g_zeroes_the_send_back_counts_and_leaves_owes(start: State) -> None:
    state: State = {
        **start, "describer_send_backs": 2, "invalid_questions": 2, "owes": "answer",
    }
    after = node_g(state)
    assert after["describer_send_backs"] == 0
    assert after["invalid_questions"] == 0
    assert after["owes"] == "answer"


@pytest.mark.parametrize(
    ("round_before", "questions", "guess_only"),
    [(9, 0, True), (4, 3, True), (8, 2, False), (0, 0, False)],
)
def test_g_sets_guess_only(
    start: State, round_before: int, questions: int, guess_only: bool
) -> None:
    """Round 10; round 5 after three questions; not round 9 after two [R16]."""
    after = node_g({**start, "round": round_before, "questions": questions})
    assert after["round"] == round_before + 1
    assert after["guess_only"] is guess_only


# F


def test_f_alias_guess_wins_with_the_alias_recorded(start: State) -> None:
    after = node_f(_guess(start, "烤牡蠣", 2))
    assert after["result"] == "right guess"
    assert after["result"] is not None and winner(after["result"]) == "Guesser wins"
    assert after["matched_name"] == "烤牡蠣"
    assert after["matched_name"] != after["names"][0]
    assert route_after_f(after) == "end"


def test_f_official_name_guess_records_the_official_name(start: State) -> None:
    after = node_f(_guess(start, "烤蚵仔", 1))
    assert after["result"] == "right guess"
    assert after["matched_name"] == after["names"][0]


@pytest.mark.parametrize("text", ["蚵仔煎", "kao o-a"])
def test_f_wrong_guess_in_round_10_loses(start: State, text: str) -> None:
    after = node_f(_guess(start, text, 10))
    assert after["result"] == "wrong guess in round 10"
    assert winner(after["result"]) == "Guesser loses"
    assert after["matched_name"] is None
    assert route_after_f(after) == "end"


def test_f_guesser_violation_loses(start: State) -> None:
    state: State = {**start, "round": 3, "violation": "Guesser"}
    after = node_f(state)
    assert after["result"] == "Guesser violation"
    assert winner(after["result"]) == "Guesser loses"
    assert route_after_f(after) == "end"


def test_f_describer_violation_wins(start: State) -> None:
    state: State = {**start, "round": 1, "violation": "Describer"}
    after = node_f(state)
    assert after["result"] == "Describer violation"
    assert winner(after["result"]) == "Guesser wins"
    assert route_after_f(after) == "end"


def test_f_reads_the_violation_before_the_guess(start: State) -> None:
    """A Describer violation in round 10 while the row still holds round 9's wrong guess."""
    state: State = {**_guess(start, "蚵仔煎", 10), "violation": "Describer"}
    assert node_f(state)["result"] == "Describer violation"


@pytest.mark.parametrize(("text", "round_"), [("蚵仔煎", 3), ("kao o-a", 4)])
def test_f_wrong_guess_before_round_10_routes_to_g(
    start: State, text: str, round_: int
) -> None:
    after = node_f(_guess(start, text, round_))
    assert after["result"] is None
    assert after["matched_name"] is None
    assert route_after_f(after) == "G"


def test_f_without_a_guess_or_violation_raises(start: State) -> None:
    with pytest.raises(ValueError, match="no guess"):
        node_f({**start, "round": 1})
