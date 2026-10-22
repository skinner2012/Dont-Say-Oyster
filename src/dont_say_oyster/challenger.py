"""Node D (Challenger) with its prompt builder and its routing, the reject loop [R13].

D asks the Challenger for a verdict on the description row [R39], [R40] and then routes: a pass
or a forced pass fills the row the Guesser reads and appends the description to the earlier
descriptions and answers (State schema, the note under the table); a reject appends it to the
earlier rejected descriptions with its reason and asks B for a new description.

Ticket-level readings (T10, settled with the author through the M2 orchestrator, 2026-10-21):
- `reason` is a required string that may be empty; on a fail an empty reason is re-asked like
  one with Chinese characters (T10 Detail, schema bullet).
- The re-ask is a second structured call at attempt 2; the verdict row keeps the first call's
  verdict, latency, token counts, and attempt number and takes only the reason from the re-ask.

Implementer's readings (T10, for the audit):
- A reason of only whitespace counts as empty.
- The re-ask shows the model its first reply as the parsed object written back as JSON; the
  wrapper does not return the raw text.
- D writes its route into the program-only `d_route` (T10 F1), since a second reject leaves the
  same verdict and reject counter as a forced pass."""

import json
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

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


def load_sections(path: Path = PROMPT_PATH) -> dict[str, str]:
    """The prompt file's `=== name ===` sections by name, each stripped of surrounding blank
    lines."""
    sections: dict[str, list[str]] = {}
    lines: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            lines = sections.setdefault(line[4:-4], [])
        elif lines is not None:
            lines.append(line)
    return {name: "\n".join(body).strip() for name, body in sections.items()}


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
    sections = load_sections()
    messages: list[BaseMessage] = [HumanMessage(build_prompt(state, sections[PROMPT]))]
    first = call_structured(settings, messages, SCHEMA, 1, client_for)
    reason: str | None = None  # only a fail keeps a reason [R40]
    reasks = 0
    if first.output["verdict"] == "fail":
        reason = first.output["reason"]
        if not _shown(reason):
            reasks = 1
            reask = [
                *messages,
                AIMessage(json.dumps(first.output, ensure_ascii=False)),
                HumanMessage(sections[REASK]),
            ]
            second = call_structured(settings, reask, SCHEMA, 2, client_for)
            reason = second.output["reason"]
            if not _shown(reason):
                reason = sections[FIXED_MESSAGE]
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
