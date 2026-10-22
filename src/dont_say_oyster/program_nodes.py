"""The program nodes A, G, F, and C (Full flow of one game) and the routing of F and C. Each
node takes the State and returns a new State; none calls a model.

Ticket-level readings (T8, settled with the author through the M2 orchestrator, 2026-10-20):
- F's route is the pure function `route_after_f` over `result`; State has no route key.
- G also zeroes the [R11] and [R17] counts, since a new round asks for new outputs; it leaves
  `owes` alone (E sets it before G runs on a valid question)."""

from collections.abc import Sequence
from typing import Literal

from dont_say_oyster.cards import Card
from dont_say_oyster.matching import has_chinese_characters
from dont_say_oyster.oracle import check_describer, check_guess
from dont_say_oyster.state import (
    QUESTION_LIMIT,
    ROUNDS,
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


def node_c(state: State) -> State:
    """C: the name check first [R21], so a reply with a card name is a violation even when it
    also has Chinese; then Chinese characters send the reply back to B, twice at most, and the
    third is a violation [R11]; a clean answer fills the Guesser's row and is appended to the
    earlier descriptions and answers [R12]; a clean description is left for D."""
    text = describer_output(state)
    if check_describer(text, card_from_state(state)).violation:
        return {**state, "violation": "Describer"}
    if has_chinese_characters(text):
        if state["describer_send_backs"] >= SEND_BACKS:
            return {**state, "violation": "Describer"}
        return {**state, "describer_send_backs": state["describer_send_backs"] + 1}
    answer = state["answer"]
    if state["owes"] == "answer" and answer is not None:
        return {
            **state,
            "guesser_input": {
                "kind": "answer",
                "text": answer["answer"],
                "latency": answer["latency"],
                "input_tokens": answer["input_tokens"],
                "output_tokens": answer["output_tokens"],
                "attempt": answer["attempt"],
            },
            "earlier_texts": [
                *state["earlier_texts"],
                {"round": state["round"], "kind": "answer", "text": answer["answer"]},
            ],
        }
    return state


def route_after_c(state: State) -> Literal["B", "D", "E", "F"]:
    """C's route: F on a violation; B when the reply has Chinese (a send-back); E for an answer,
    skipping the Challenger [R12]; D for a description (in M2 a description always goes to D)."""
    if state["violation"] == "Describer":
        return "F"
    if has_chinese_characters(describer_output(state)):
        return "B"
    return "E" if state["owes"] == "answer" else "D"
