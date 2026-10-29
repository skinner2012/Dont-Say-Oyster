"""The program nodes A, G, F, and C (Full flow of one game) and the routing of F and C. Each
node takes the State and returns a new State; none calls a model. C and its route take the
Challenger toggle (`SPEC.md` Ablation Design): on, a clean description goes to D; off, C fills
the Guesser's row itself and routes to E. The toggle defaults to on, V2's value.

Readings settled with the author on 2026-10-20:
- F's route is the pure function `route_after_f` over `result`; State has no route key.
- G also zeroes the [R11] and [R17] counts, since a new round asks for new outputs; it leaves
  `owes` alone (E sets it before G runs on a valid question)."""

from collections.abc import Sequence
from typing import Literal

from dont_say_oyster.cards import Card
from dont_say_oyster.matching import has_chinese_characters
from dont_say_oyster.oracle import check_describer, check_guess
from dont_say_oyster.state import (
    CHINESE_CHARACTERS,
    QUESTION_LIMIT,
    ROUNDS,
    Answer,
    Description,
    SentBack,
    State,
    card_from_state,
    describer_output,
    initial_state,
)


def node_a(card_id: str, cards: Sequence[Card]) -> State:
    """A: draw the card `card_id` from `cards` into a new State. Raises KeyError naming the id
    when no card has it."""
    for card in cards:
        if card.card_id == card_id:
            return initial_state(card)
    raise KeyError(f"no card with id {card_id}")


def node_g(state: State) -> State:
    """G: a new round [R14]; zero the counters scoped to the round or to the output being asked
    for; guess only after three questions and always in round 10 [R16]."""
    round_ = state["round"] + 1
    return {
        **state,
        "round": round_,
        "rejects": 0,
        "lookup_count": 0,
        "describer_send_backs": 0,
        "invalid_questions": 0,
        "guess_only": state["questions"] >= QUESTION_LIMIT or round_ >= ROUNDS,
    }


def node_f(state: State) -> State:
    """F: the outcome [R23]. A violation decides it first; otherwise the Guesser's guess is
    checked [R20], [R5]: right wins, recording the name it matched; wrong in round 10 loses;
    wrong earlier leaves no result. Raises ValueError when there is neither a violation nor a
    guess."""
    if state["violation"] == "Describer":
        return {**state, "result": "Describer violation"}
    if state["violation"] == "Guesser":
        return {**state, "result": "Guesser violation"}
    output = state["guesser_output"]
    if output is None or output["kind"] != "guess":
        raise ValueError(f"F reached in round {state['round']} with no guess and no violation")
    check = check_guess(output["text"], card_from_state(state))
    if check.correct:
        return {**state, "result": "right guess", "matched_name": check.matched}
    if state["round"] >= ROUNDS:
        return {**state, "result": "wrong guess in round 10"}
    return state


def route_after_f(state: State) -> Literal["G", "end"]:
    """F's route: "end" on one of the four outcomes, otherwise G for a new round."""
    return "G" if state["result"] is None else "end"


SEND_BACKS = 2  # [R11]


def _to_guesser(
    state: State, kind: Literal["description", "answer"], text: str, output: Description | Answer
) -> State:
    """Fill the row the Guesser reads with `output`'s metrics and append `text` to the earlier
    descriptions and answers (State schema, the note under the table)."""
    return {
        **state,
        "guesser_input": {
            "kind": kind,
            "text": text,
            "latency": output["latency"],
            "input_tokens": output["input_tokens"],
            "output_tokens": output["output_tokens"],
            "attempt": output["attempt"],
        },
        "earlier_texts": [*state["earlier_texts"], {"round": state["round"], "kind": kind,
                                                    "text": text}],
    }


def _last_b_ordinal(state: State) -> int:
    """The ordinal of B's last call, the one whose reply C is checking. Raises ValueError when
    B has made no call."""
    for entry in reversed(state["calls"]):
        if entry["node"] == "B":
            return entry["ordinal"]
    raise ValueError(f"C reached in round {state['round']} with no call from B")


def node_c(state: State, challenger: bool = True) -> State:
    """C: the name check first [R21], so a reply with a card name is a violation even when it
    also has Chinese; then Chinese characters send the reply back to B, twice at most, each
    send-back appended to `sent_back`, and the third is a violation, not a send-back [R11]; a
    clean answer fills the Guesser's row and is appended to the earlier descriptions and answers
    [R12]. A clean description is left for D when the Challenger is on (`SPEC.md` Ablation
    Design, V2); with it off, C fills the row and appends the description itself, as D does on a
    pass, since no node stands between C and E."""
    text = describer_output(state)
    if check_describer(text, card_from_state(state)).violation:
        return {**state, "violation": "Describer"}
    if has_chinese_characters(text):
        if state["describer_send_backs"] >= SEND_BACKS:
            return {**state, "violation": "Describer"}
        sent_back: SentBack = {
            "round": state["round"],
            "node": "C",
            "kind": state["owes"],
            "text": text,
            "ordinal": _last_b_ordinal(state),
            "reason": CHINESE_CHARACTERS,
            "replaced": False,
        }
        return {
            **state,
            "describer_send_backs": state["describer_send_backs"] + 1,
            "sent_back": [*state["sent_back"], sent_back],
        }
    answer = state["answer"]
    if state["owes"] == "answer" and answer is not None:
        return _to_guesser(state, "answer", answer["answer"], answer)
    description = state["description"]
    if not challenger and description is not None:
        return _to_guesser(state, "description", description["description"], description)
    return state


def route_after_c(state: State, challenger: bool = True) -> Literal["B", "D", "E", "F"]:
    """C's route: F on a violation; B when the reply has Chinese (a send-back); E for an answer,
    skipping the Challenger [R12]; for a description, D when the Challenger is on and E when it
    is off (Full flow of one game, Transitions that differ between variants)."""
    if state["violation"] == "Describer":
        return "F"
    if has_chinese_characters(describer_output(state)):
        return "B"
    return "E" if state["owes"] == "answer" or not challenger else "D"
