"""Node H, the memory summary (Full flow of one game, the H row): at game end the Describer and
the Guesser each make one structured call that returns the role's new memory entry and, from
game six on, its updated rolling summary of the older entries; the program then advances each
role's memory and writes the role's file for this game (Cross-game memory definition, Storage).

The prompts are the author's files `prompts/describer_memory.txt` and
`prompts/guesser_memory.txt`, read by their `=== name ===` sections: the `prompt` section with
`{task}` replaced by the task section matching the schema (`task: entry` for games 1 to 5,
`task: entry and summary` from game six on). The `conventions` section of each file names every
slot and never goes to the model.

What each prompt holds (Information isolation, Disclosure rule):
- The Describer's: the card's official name, aliases, English names, and forbidden words [R27];
  the game as the Describer saw it, rendered by `describer.py`'s helpers (every description and
  answer that reached the Guesser, every guess and valid question with the last one, every
  rejected description with its reason, the round counter); in a game that ended by Describer
  violation, the violating description or answer, which never reached the Guesser ([R11],
  [R21]); the game result, the F outcome's name; the Describer's memory as read at game start
  (`memory.render`).
- The Guesser's: the game as the Guesser saw it, rendered by `guesser.py`'s helpers (every
  description and answer it received, its guesses with their confidence and its valid
  questions, the round and question counters); each corpus lookup by its arguments and the
  number of results it returned, or the message it got, never the returned entries; who won and
  who lost as `winner` says it, never the game result; the Guesser's memory as read at game
  start. No card row reaches it, so of the snack names only the Guesser's own guesses can.
- From game six on, both task sections name the game of the oldest entry, the one that leaves
  the latest five when this game's entry is added and is folded into the summary, or (none)
  when the memory holds fewer than five entries; the summary is asked for by game number
  whatever the entry count.

Each call is attempt 1 [R26] and its output is accepted as returned: the checks on the entry
and the summary ([R6], the Check rule) are not made here. Both calls are made before either
file is written, and each passes the game's last round in its run metadata, the round its
`calls` entry carries (`SPEC.md` Metrics, Per model call). The two memory rows keep the
memories as read at game start; what H accepted goes into the program-only `describer_accepted`
and `guesser_accepted`. H ends the game; there is no route."""

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from dont_say_oyster import prompt_sections
from dont_say_oyster.cards import REPO_ROOT
from dont_say_oyster.describer import _earlier, _lines, _list, _rejected
from dont_say_oyster.guesser import _earlier_guesses, _earlier_texts
from dont_say_oyster.llm import ClientFor, ModelSettings, Reply, call_structured, ollama_client
from dont_say_oyster.memory import LATEST, Memory, Role, advance, render, write_memory
from dont_say_oyster.state import Accepted, Lookup, State, describer_output, winner, with_call

DESCRIBER_PROMPT_PATH = REPO_ROOT / "prompts" / "describer_memory.txt"
GUESSER_PROMPT_PATH = REPO_ROOT / "prompts" / "guesser_memory.txt"
SUMMARY_FROM = 6  # the rolling summary is written from game six on (Cross-game memory definition)
ATTEMPT = 1  # [R26]; the Check rule's redos are not made here
NONE = "(none)"

_TEXT: dict[str, Any] = {"type": "string", "minLength": 1}

ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["entry"],
    "additionalProperties": False,
    "properties": {"entry": _TEXT},
}

ENTRY_AND_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["entry", "summary"],
    "additionalProperties": False,
    "properties": {"entry": _TEXT, "summary": _TEXT},
}


def _with_summary(state: State) -> bool:
    return state["game"] >= SUMMARY_FROM


def schema(state: State) -> dict[str, Any]:
    """The schema of this game's H calls: the entry alone for games 1 to 5, the entry and the
    summary from game six on."""
    return ENTRY_AND_SUMMARY_SCHEMA if _with_summary(state) else ENTRY_SCHEMA


def _task(state: State, sections: dict[str, str], memory: Memory) -> str:
    """The task section matching the schema; from game six on its `{fold}` slot names the game
    of the oldest entry, the one that leaves the latest five, or (none) when there are fewer."""
    if not _with_summary(state):
        return sections["task: entry"]
    entries = memory["entries"]
    fold = f"Game {entries[0]['game']}" if len(entries) >= LATEST else NONE
    return sections["task: entry and summary"].format_map({"fold": fold})


def describer_prompt(state: State, sections: dict[str, str]) -> str:
    """The Describer's H prompt, from its items in State alone (Information isolation) and the
    game result (Disclosure rule)."""
    result = state["result"]
    if result is None:
        raise ValueError("H reached with no game result")
    official_name, *aliases = state["names"]
    return sections["prompt"].format_map({
        "official_name": official_name,
        "aliases": _list(aliases),
        "english_names": _list(state["english_names"]),
        "forbidden_words": _list(state["forbidden_words"]),
        "result": result,
        "rounds": state["round"],
        "descriptions_and_answers": _lines([_earlier(item) for item in state["earlier_texts"]]),
        "guesses_and_questions": _lines([_earlier(item) for item in state["earlier_guesses"]]),
        "rejected_descriptions": _lines([_rejected(item) for item in state["rejected"]]),
        "violating_reply": (
            describer_output(state) if result == "Describer violation" else NONE
        ),
        "memory": render(state["describer_memory"]),
        "task": _task(state, sections, state["describer_memory"]),
    })


def _lookup(item: Lookup) -> str:
    """One lookup as its arguments and what came back, without the returned entries."""
    arguments = json.dumps(item["arguments"], ensure_ascii=False, sort_keys=True)
    result = item["result"]
    if isinstance(result, str):
        found = f"not searched: {result}"
    else:
        count = len(result["results"])
        found = f"{count} result{'' if count == 1 else 's'}"
        if result["more_results"]:
            found += ", and more matched"
    return f"Round {item['round']}, {item['name']} {arguments}: {found}"


def guesser_prompt(state: State, sections: dict[str, str]) -> str:
    """The Guesser's H prompt, from its items in State alone (Information isolation) and who won
    and who lost (Disclosure rule)."""
    result = state["result"]
    if result is None:
        raise ValueError("H reached with no game result")
    lookups = [_lookup(item) for item in state["lookups"]]
    return sections["prompt"].format_map({
        "winner": winner(result),
        "rounds": state["round"],
        "questions": state["questions"],
        # At game end no description or answer is waiting for a reply, so every one the Guesser
        # received is listed, the last round's included.
        "descriptions_and_answers": _earlier_texts({**state, "guesser_input": None}),
        "guesses_and_questions": _earlier_guesses(state),
        "lookups": "\n".join(lookups) or NONE,
        "memory": render(state["guesser_memory"]),
        "task": _task(state, sections, state["guesser_memory"]),
    })


def _call(
    state: State, settings: ModelSettings, prompt: str, client_for: ClientFor
) -> Reply[dict[str, Any]]:
    return call_structured(
        settings,
        [HumanMessage(prompt)],
        schema(state),
        ATTEMPT,
        client_for,
        metadata={"round": state["round"]},
    )


def _accepted(state: State, reply: Reply[dict[str, Any]]) -> Accepted:
    return {
        "entry": reply.output["entry"],
        "summary": reply.output["summary"] if _with_summary(state) else None,
    }


def _write(directory: Path, role: Role, state: State, memory: Memory, accepted: Accepted) -> None:
    advanced = advance(memory, state["game"], accepted["entry"], accepted["summary"])
    write_memory(directory, role, state["game"], advanced)


def node_h(
    state: State,
    describer_settings: ModelSettings,
    guesser_settings: ModelSettings,
    directory: Path,
    client_for: ClientFor = ollama_client,
    describer_sections: dict[str, str] | None = None,
    guesser_sections: dict[str, str] | None = None,
) -> State:
    """H: the Describer's call, then the Guesser's, each with its own settings; then each role's
    memory advanced with what it returned and written as its file for this game under
    `directory` (Storage). Appends both calls to `calls` and writes what was accepted into the
    two program-only rows; the memory rows are left as read at game start."""
    if describer_sections is None:
        describer_sections = prompt_sections.sections(DESCRIBER_PROMPT_PATH)
    if guesser_sections is None:
        guesser_sections = prompt_sections.sections(GUESSER_PROMPT_PATH)
    describer = _call(
        state, describer_settings, describer_prompt(state, describer_sections), client_for
    )
    guesser = _call(state, guesser_settings, guesser_prompt(state, guesser_sections), client_for)
    calls = with_call(state["calls"], "H", describer_settings, state["round"], describer)
    calls = with_call(calls, "H", guesser_settings, state["round"], guesser)
    describer_accepted = _accepted(state, describer)
    guesser_accepted = _accepted(state, guesser)
    _write(directory, "describer", state, state["describer_memory"], describer_accepted)
    _write(directory, "guesser", state, state["guesser_memory"], guesser_accepted)
    return {
        **state,
        "calls": calls,
        "describer_accepted": describer_accepted,
        "guesser_accepted": guesser_accepted,
    }
