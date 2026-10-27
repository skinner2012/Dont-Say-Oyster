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
from dont_say_oyster.state import State, Verdict

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


def _shown(reason: str) -> bool:
    """Whether a fail's reason can go into the verdict row as it is [R40]."""
    return bool(reason.strip()) and not has_chinese_characters(reason)


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
    reason: str | None = None  # only a fail keeps a reason [R40]
    reasks = 0
    if first.output["verdict"] == "fail":
        reason = first.output["reason"]
        if not _shown(reason):
            reasks = 1
            reask = [
                *messages,
                AIMessage(json.dumps(first.output, ensure_ascii=False)),
                HumanMessage(texts[REASK]),
            ]
            second = call_structured(settings, reask, SCHEMA, 2, client_for, metadata=round_key)
            reason = second.output["reason"]
            if not _shown(reason):
                reason = texts[FIXED_MESSAGE]
    verdict: Verdict = {
        "verdict": first.output["verdict"],
        "reason": reason,
        "latency": first.latency,
        "input_tokens": first.input_tokens,
        "output_tokens": first.output_tokens,
        "attempt": first.attempt,
    }
    state = {**state, "verdict": verdict, "reason_reasks": reasks}
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
