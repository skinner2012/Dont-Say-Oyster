"""Node D (Challenger) with its prompt builder and its routing, the reject loop [R13].

D asks the Challenger for a verdict on the description row [R39], [R40] and then routes: a pass
or a forced pass fills the row the Guesser reads and appends the description to the earlier
descriptions and answers (State schema, the note under the table); a reject appends it to the
earlier rejected descriptions with its reason and asks B for a new description.

Readings settled with the author on 2026-10-21:
- `reason` is a required string that may be empty; on a fail an empty reason is re-asked like
  one with Chinese characters.
- The re-ask is a second structured call at attempt 2; the verdict row keeps the first call's
  verdict, latency, token counts, and attempt number and takes only the reason from the re-ask.
- Both calls pass the round in their run metadata, so each span says which round it belongs to
  without reading its neighbours in the trace (`SPEC.md` Goals, Evaluation and observability).

Every visit appends its one or two calls to `calls` and its verdict, as the verdict row shows
it, to `verdicts`; a re-asked fail reason [R40] is appended to `sent_back` with why it was
re-asked (Chinese characters, or empty), and so is the second reason when the fixed message
replaces it, marked `replaced`, since the record shows what validation caught.

Implementer's readings, for the audit:
- A reason of only whitespace counts as empty.
- The re-ask shows the model its first reply as the parsed object written back as JSON; the
  wrapper does not return the raw text.
- D writes its route into the program-only `d_route`, since a second reject leaves the
  same verdict and reject counter as a forced pass."""

import json
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from dont_say_oyster import prompt_sections
from dont_say_oyster.cards import REPO_ROOT
from dont_say_oyster.llm import ClientFor, ModelSettings, call_structured, ollama_client
from dont_say_oyster.matching import has_chinese_characters
from dont_say_oyster.state import (
    CHINESE_CHARACTERS,
    EMPTY,
    SentBack,
    State,
    Verdict,
    VerdictEntry,
    with_call,
)

PROMPT_PATH = REPO_ROOT / "prompts" / "challenger.txt"
PROMPT = "prompt"
REASK = "re-ask [R40]"
FIXED_MESSAGE = "fixed message [R40]"
REJECT_LIMIT = 2  # [R13]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "reason"],
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "reason": {"type": "string"},
    },
}


def _slot(items: list[str]) -> str:
    return ", ".join(items) if items else "(none)"


def build_prompt(state: State, template: str) -> str:
    """The Challenger's prompt: its items in Information isolation and nothing else [R34]."""
    description = state["description"]
    if description is None:
        raise ValueError("D reached with no description")
    official_name, *aliases = state["names"]
    return template.format(
        official_name=official_name,
        aliases=_slot(aliases),
        distractors=_slot(state["distractors"]),
        description=description["description"] or "(none)",
    )


def _caught(reason: str) -> str | None:
    """Why a fail's reason cannot go into the verdict row as it is [R40], or None when it
    can."""
    if not reason.strip():
        return EMPTY
    if has_chinese_characters(reason):
        return CHINESE_CHARACTERS
    return None


def _sent_back(
    state: State, reason: str, ordinal: int, caught: str, replaced: bool
) -> SentBack:
    """The `sent_back` entry for a fail reason as the model wrote it [R40]."""
    return {
        "round": state["round"],
        "node": "D",
        "kind": "reason",
        "text": reason,
        "ordinal": ordinal,
        "reason": caught,
        "replaced": replaced,
    }


def node_d(
    state: State, settings: ModelSettings, client_for: ClientFor = ollama_client
) -> State:
    """D: the verdict on the description row [R40], then a pass, a reject, or a forced pass
    [R13]."""
    description = state["description"]
    if description is None:
        raise ValueError("D reached with no description")
    texts = prompt_sections.sections(PROMPT_PATH)
    messages: list[BaseMessage] = [HumanMessage(build_prompt(state, texts[PROMPT]))]
    round_key = {"round": state["round"]}
    first = call_structured(settings, messages, SCHEMA, 1, client_for, metadata=round_key)
    calls = with_call(state["calls"], "D", settings, state["round"], first)
    ordinal = calls[-1]["ordinal"]
    sent_back = list(state["sent_back"])
    reason: str | None = None  # only a fail keeps a reason [R40]
    reasks = 0
    if first.output["verdict"] == "fail":
        reason = first.output["reason"]
        caught = _caught(reason)
        if caught is not None:
            reasks = 1
            sent_back.append(_sent_back(state, reason, ordinal, caught, replaced=False))
            reask = [
                *messages,
                AIMessage(json.dumps(first.output, ensure_ascii=False)),
                HumanMessage(texts[REASK]),
            ]
            second = call_structured(settings, reask, SCHEMA, 2, client_for, metadata=round_key)
            calls = with_call(calls, "D", settings, state["round"], second)
            reason = second.output["reason"]
            caught = _caught(reason)
            if caught is not None:
                sent_back.append(
                    _sent_back(state, reason, calls[-1]["ordinal"], caught, replaced=True)
                )
                reason = texts[FIXED_MESSAGE]
    verdict: Verdict = {
        "verdict": first.output["verdict"],
        "reason": reason,
        "latency": first.latency,
        "input_tokens": first.input_tokens,
        "output_tokens": first.output_tokens,
        "attempt": first.attempt,
    }
    entry: VerdictEntry = {
        "round": state["round"],
        "verdict": verdict["verdict"],
        "reason": reason,
        "ordinal": ordinal,
    }
    state = {
        **state,
        "verdict": verdict,
        "reason_reasks": reasks,
        "calls": calls,
        "sent_back": sent_back,
        "verdicts": [*state["verdicts"], entry],
    }
    if reason is not None and state["rejects"] < REJECT_LIMIT:
        return {
            **state,
            "rejects": state["rejects"] + 1,
            "rejected": [
                *state["rejected"],
                {
                    "round": state["round"],
                    "description": description["description"],
                    "reason": reason,
                },
            ],
            "describer_send_backs": 0,
            "d_route": "B",
        }
    return {
        **state,
        "forced_passes": state["forced_passes"] + (1 if reason is not None else 0),
        "guesser_input": {
            "kind": "description",
            "text": description["description"],
            "latency": description["latency"],
            "input_tokens": description["input_tokens"],
            "output_tokens": description["output_tokens"],
            "attempt": description["attempt"],
        },
        "earlier_texts": [
            *state["earlier_texts"],
            {"round": state["round"], "kind": "description", "text": description["description"]},
        ],
        "d_route": "E",
    }


def route_after_d(state: State) -> Literal["B", "E"]:
    """D's route, as D wrote it: E on a pass or a forced pass, B on a reject. Raises ValueError
    when D has not run."""
    route = state["d_route"]
    if route is None:
        raise ValueError("route_after_d reached before D wrote a route")
    return route
