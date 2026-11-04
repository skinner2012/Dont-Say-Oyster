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

The Check rule (Cross-game memory definition): after each call the entry and, from game six on,
the summary are checked separately with `oracle.check_memory`, the Describer's for Chinese
characters [R6] and the Guesser's also for the card's official name, aliases, and English names
[R22]; a failure in either text sends the whole output back. A send-back is a new request made
of the prompt, the model's previous reply as its own message, and the file's `fixed message`
section, with the attempt number one higher [R26], at most `REDO_LIMIT` times, so a role makes
one, two, or three calls; when the third output still fails, that role's game is not written and
its file for this game holds the previous game's memory, copied forward with this game's number.
The fixed message never says which check failed or quotes what was found (Disclosure rule); the
reasons are kept in State for the record only. A blank entry or summary (whitespace only, which
the schema's `minLength` lets through) is a model error like the empty string the schema
refuses: LLMError, the game stops, no file (`SPEC.md` Recovery, forks, and replay).

Both roles' loops finish before either memory is advanced or written, and each call passes the
game's last round in its run metadata, the round its `calls` entry carries (`SPEC.md` Metrics,
Per model call), so a model error in any call leaves neither file. The two memory rows keep the
memories as read at game start; what H did goes into the program-only `describer_h` and
`guesser_h`. H ends the game; there is no route."""

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from dont_say_oyster import prompt_sections
from dont_say_oyster.cards import REPO_ROOT, Card
from dont_say_oyster.describer import _earlier, _lines, _list, _rejected
from dont_say_oyster.guesser import _earlier_guesses, _earlier_texts
from dont_say_oyster.llm import ClientFor, LLMError, ModelSettings, call_structured, ollama_client
from dont_say_oyster.memory import LATEST, Memory, Role, advance, render, write_memory
from dont_say_oyster.oracle import check_memory
from dont_say_oyster.state import (
    CARD_ENGLISH_NAMES,
    CARD_NAMES,
    CHINESE_CHARACTERS,
    Call,
    HFailed,
    HResult,
    Lookup,
    State,
    card_from_state,
    describer_output,
    winner,
    with_call,
)

DESCRIBER_PROMPT_PATH = REPO_ROOT / "prompts" / "describer_memory.txt"
GUESSER_PROMPT_PATH = REPO_ROOT / "prompts" / "guesser_memory.txt"
SUMMARY_FROM = 6  # the rolling summary is written from game six on (Cross-game memory definition)
REDO_LIMIT = 2  # redos per role under the Check rule (Cross-game memory definition)
FIXED_MESSAGE = "fixed message"  # the section sent after a failed check
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


def _reasons(entry: str, summary: str | None, card: Card, role: Role) -> list[str]:
    """Why an output fails the Check rule: the union over the entry and the summary, each checked
    on its own so nothing matches across their join [R22], each reason once in a fixed order;
    empty when the output passes."""
    checks = [check_memory(entry, card, role)]
    if summary is not None:
        checks.append(check_memory(summary, card, role))
    reasons = []
    if any(c.has_chinese for c in checks):
        reasons.append(CHINESE_CHARACTERS)
    if any(c.names for c in checks):
        reasons.append(CARD_NAMES)
    if any(c.english_names for c in checks):
        reasons.append(CARD_ENGLISH_NAMES)
    return reasons


def _loop(
    state: State,
    role: Role,
    settings: ModelSettings,
    prompt: str,
    sections: dict[str, str],
    calls: list[Call],
    client_for: ClientFor,
) -> tuple[list[Call], HResult]:
    """One role's calls under the Check rule: the first with the prompt alone, each redo with the
    prompt, the previous reply, and the fixed message, attempts 1, 2, 3 [R26], every call
    appended to `calls`; returns the calls and what H did for the role. Raises LLMError on a
    blank entry or summary, as the wrapper does on an empty one."""
    card = card_from_state(state)
    messages: list[BaseMessage] = [HumanMessage(prompt)]
    failed: list[HFailed] = []
    for attempt in range(1, REDO_LIMIT + 2):
        reply = call_structured(
            settings,
            messages,
            schema(state),
            attempt,
            client_for,
            metadata={"round": state["round"]},
        )
        calls = with_call(calls, "H", settings, state["round"], reply)
        entry: str = reply.output["entry"]
        summary: str | None = reply.output["summary"] if _with_summary(state) else None
        for field, text in (("entry", entry), ("summary", summary)):
            if text is not None and not text.strip():
                raise LLMError(f"{settings.role}: memory {field} is blank")
        reasons = _reasons(entry, summary, card, role)
        if not reasons:
            return calls, {
                "written": True,
                "redos": attempt - 1,
                "entry": entry,
                "summary": summary,
                "failed": failed,
            }
        failed.append({
            "attempt": attempt,
            "ordinal": calls[-1]["ordinal"],
            "entry": entry,
            "summary": summary,
            "reasons": reasons,
        })
        messages = [
            HumanMessage(prompt),
            AIMessage(json.dumps(reply.output, ensure_ascii=False)),
            HumanMessage(sections[FIXED_MESSAGE]),
        ]
    return calls, {
        "written": False, "redos": REDO_LIMIT, "entry": None, "summary": None, "failed": failed,
    }


def _after(state: State, memory: Memory, result: HResult) -> Memory:
    """The memory to write for this game: advanced with the accepted entry and summary, or, when
    the game was not written for the role, the memory as read at game start (the copy-forward of
    the Check rule; `write_memory` stamps this game's number on it)."""
    if not result["written"] or result["entry"] is None:
        return memory
    return advance(memory, state["game"], result["entry"], result["summary"])


def node_h(
    state: State,
    describer_settings: ModelSettings,
    guesser_settings: ModelSettings,
    directory: Path,
    client_for: ClientFor = ollama_client,
    describer_sections: dict[str, str] | None = None,
    guesser_sections: dict[str, str] | None = None,
) -> State:
    """H: the Describer's calls under the Check rule, then the Guesser's, each role with its own
    settings; then each role's memory advanced with what was accepted, or kept as read at game
    start when the role's game was not written, and only then each written as the role's file
    for this game under `directory` (Storage), so an error before the writes leaves neither file.
    Appends every call to `calls` and writes what H did into the two program-only rows; the
    memory rows are left as read at game start."""
    if describer_sections is None:
        describer_sections = prompt_sections.sections(DESCRIBER_PROMPT_PATH)
    if guesser_sections is None:
        guesser_sections = prompt_sections.sections(GUESSER_PROMPT_PATH)
    calls, describer_h = _loop(
        state, "describer", describer_settings, describer_prompt(state, describer_sections),
        describer_sections, state["calls"], client_for,
    )
    calls, guesser_h = _loop(
        state, "guesser", guesser_settings, guesser_prompt(state, guesser_sections),
        guesser_sections, calls, client_for,
    )
    to_write: tuple[tuple[Role, Memory], ...] = (
        ("describer", _after(state, state["describer_memory"], describer_h)),
        ("guesser", _after(state, state["guesser_memory"], guesser_h)),
    )
    for role, memory in to_write:
        write_memory(directory, role, state["game"], memory)
    return {**state, "calls": calls, "describer_h": describer_h, "guesser_h": guesser_h}
