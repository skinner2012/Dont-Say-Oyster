"""The JSONL record of one game (`SPEC.md` Implementation, Experiment result format): built from
the final State, the variant, and the three roles' settings, and appended to the output file as
one line, so the game stands without its trace (`SPEC.md` Recovery, forks, and replay, Trace
loss). Its format is `data/records/schema.json`, in which every object lists every one of its
fields as required and allows no other, so a record is complete when it validates.

The record, top level: the card id, the card's official name (so `matched_name` reads as the
official name or an alias without the cards file), the variant, the F outcome, `matched_name`
(the card name a right guess equals, `SPEC.md` Metrics, Per game; null otherwise), `counters`
(the round, question, and forced pass counters as F left them), `rounds`, `calls` (State's list
as it is: every model call with the per-call values of `SPEC.md` Metrics, Per model call, H's
two included), `settings` (each role's model tag, num_ctx, thinking value, and keep_alive, and
the temperature, as the command resolved them, since a game run by hand has no batch manifest to
say so), and `memory`.

`memory` is null when the variant's memory toggle is off, so the schema keeps one shape; with it
on, an object with the game number and one object per role (`describer`, `guesser`) built from
the role's program-only H row (Cross-game memory definition, Check rule): `entry` (the accepted
entry, null when the game was not written for the role), `summary` (the accepted rolling
summary, null before game six and when not written), `redos` (0 to 2), `written`, `failed`
(every output the Check rule failed, the refused third included, each with its attempt, the
ordinal of the call that produced it, both texts, and its reasons; those with attempt at most
`redos` were sent back), and `tokens`, the memory token count the command measured after the
game (`SPEC.md` Metrics, Per game; `llm.ollama_token_count`): the block the role read at game
start, which the caller passes in, since the count is a measurement outside the graph and not a
State row.

`rounds` has one entry per round begun: G increments the round counter before B, so
`counters.rounds` counts rounds begun, and a Describer violation in a round's first description
leaves a round whose text never reached the Guesser [R14]; that round's entry has no reached
text, so either count can be derived from the list. Each entry holds every key, null or empty
where it does not apply:
- `owed`: what the Describer was asked for [R10], an answer when the previous round's entry in
  the earlier guesses and questions is a question, else a description;
- `reached_text`: the description or answer that reached the Guesser, from the earlier
  descriptions and answers; null when the round ended in C;
- `rejected`, `verdicts`, `sent_back`, and `lookups`: the round's items of State's lists, in
  order, without their round key, which the entry carries; a lookup keeps its call index, tool
  name, arguments, status, and result, not the call's metrics, which `calls` holds [R26];
- `guesser_output`: the guess or valid question, with its confidence on a guess [R48], from
  the earlier guesses and questions; null when the round ended before one;
- `violating_question`: the third invalid question when the round ended in a Guesser violation
  [R17] (the Guesser's output row); `violating_text`: the description or answer when it ended
  in a Describer violation [R11], [R21] (the Describer's row for what it owed). Only the last
  round's entry can hold either."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dont_say_oyster.graph import TOGGLES, RoleSettings, Variant
from dont_say_oyster.llm import ModelSettings
from dont_say_oyster.memory import Role
from dont_say_oyster.state import HResult, State, describer_output

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "records" / "schema.json"


def _role(settings: ModelSettings) -> dict[str, Any]:
    return {
        "model": settings.model,
        "num_ctx": settings.num_ctx,
        "thinking": settings.thinking,
        "keep_alive": settings.keep_alive,
    }


def _settings(settings: RoleSettings) -> dict[str, Any]:
    """The roles' settings and the one temperature (`SPEC.md` Implementation, Temperature
    policy). Raises ValueError when the roles' temperatures differ, since the record has one."""
    roles = (settings.describer, settings.challenger, settings.guesser)
    temperatures = {role.temperature for role in roles}
    if len(temperatures) != 1:
        raise ValueError(f"the roles' temperatures differ: {sorted(temperatures)}")
    return {
        "describer": _role(settings.describer),
        "challenger": _role(settings.challenger),
        "guesser": _role(settings.guesser),
        "temperature": temperatures.pop(),
    }


def _without_round(items: list[Any], round_: int) -> list[dict[str, Any]]:
    """The items of round `round_`, in order, each without its round key."""
    return [
        {key: value for key, value in item.items() if key != "round"}
        for item in items
        if item["round"] == round_
    ]


def _rounds(state: State) -> list[dict[str, Any]]:
    reached = {item["round"]: item["text"] for item in state["earlier_texts"]}
    guesser = {item["round"]: item for item in state["earlier_guesses"]}
    last = state["round"]
    entries = []
    for round_ in range(1, last + 1):
        previous = guesser.get(round_ - 1)
        output = guesser.get(round_)
        violating_question = None
        violating_text = None
        if round_ == last and state["result"] == "Guesser violation":
            row = state["guesser_output"]
            if row is None:
                raise ValueError("a Guesser violation with no Guesser output")
            violating_question = row["text"]
        if round_ == last and state["result"] == "Describer violation":
            violating_text = describer_output(state)
        entries.append({
            "round": round_,
            "owed": "answer" if previous is not None and previous["kind"] == "question"
            else "description",
            "reached_text": reached.get(round_),
            "rejected": _without_round(state["rejected"], round_),
            "verdicts": _without_round(state["verdicts"], round_),
            "sent_back": _without_round(state["sent_back"], round_),
            "lookups": [
                {key: lookup[key] for key in ("call", "name", "arguments", "status", "result")}
                for lookup in state["lookups"]
                if lookup["round"] == round_
            ],
            "guesser_output": None if output is None else {
                "kind": output["kind"], "text": output["text"], "confidence": output["confidence"]
            },
            "violating_question": violating_question,
            "violating_text": violating_text,
        })
    return entries


def _memory_role(result: HResult | None, role: Role, tokens: int) -> dict[str, Any]:
    """One role's `memory` object from its H row and its memory token count. Raises ValueError
    when H has not run for the role."""
    if result is None:
        raise ValueError(f"the {role}'s memory row is empty: H has not run")
    return {
        "entry": result["entry"],
        "summary": result["summary"],
        "redos": result["redos"],
        "written": result["written"],
        "failed": result["failed"],
        "tokens": tokens,
    }


def _memory(state: State, memory_tokens: Mapping[Role, int]) -> dict[str, Any]:
    return {
        "game": state["game"],
        "describer": _memory_role(state["describer_h"], "describer", memory_tokens["describer"]),
        "guesser": _memory_role(state["guesser_h"], "guesser", memory_tokens["guesser"]),
    }


def build_record(
    state: State,
    variant: Variant,
    settings: RoleSettings,
    memory_tokens: Mapping[Role, int] | None = None,
) -> dict[str, Any]:
    """The record of the game whose final State is `state`, played in `variant` with
    `settings`; `memory_tokens`, each role's memory token count, is given exactly when the
    variant's memory toggle is on. Raises ValueError when the game has no result, the roles'
    temperatures differ, `memory_tokens` disagrees with the toggle, or memory is on and H has
    not run."""
    if state["result"] is None:
        raise ValueError("the game ended with no result")
    if TOGGLES[variant].memory and memory_tokens is None:
        raise ValueError(f"{variant} plays with memory but no memory token counts were given")
    if not TOGGLES[variant].memory and memory_tokens is not None:
        raise ValueError(f"{variant} plays without memory but memory token counts were given")
    return {
        "card_id": state["card_id"],
        "official_name": state["names"][0],
        "variant": variant,
        "result": state["result"],
        "matched_name": state["matched_name"],
        "counters": {
            "rounds": state["round"],
            "questions": state["questions"],
            "forced_passes": state["forced_passes"],
        },
        "rounds": _rounds(state),
        "calls": state["calls"],
        "settings": _settings(settings),
        "memory": None if memory_tokens is None else _memory(state, memory_tokens),
    }


def write_record(record: dict[str, Any], path: Path) -> None:
    """Append `record` to `path` as one JSON line, created when missing: no indent and no
    newline inside the line, since `json.dumps` escapes those in strings; Chinese is written as
    it is."""
    line = json.dumps(record, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
