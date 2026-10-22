"""Node E, the Guesser (Full flow of one game): the prompt built from `prompts/guesser.txt`, the
tool loop with the search tool bound [R43], [R49], the separate structured call for a question
or a guess [R47], [R48], the invalid-question loop [R17], and E's routing.

E is a plain `State -> State` function taking its ModelSettings, the loaded corpus, and the
client factory as parameters; no model tag is fixed here (T13 passes the constants).

Ticket-level readings (T12, from the ticket and the M2 orchestrator, 2026-10-21):
- The prompt file is parsed by its `=== name ===` sections; the model gets the `prompt`
  section with `{task}` replaced by the task section matching the schema. The slots are the
  Guesser's items in Information isolation: the round and question counters, the earlier
  descriptions and answers (without this round's item, which C and D append before E runs),
  the earlier guesses and valid questions, and this round's description or answer. An empty
  slot prints (none). Lookup results have no slot: this round's results reach the model as tool
  results in the message history, and earlier rounds' results are not shown.
- The tool loop: the history starts as the prompt; each reply's tool calls are handled in
  order: while fewer than five lookups have been made this round, the call is run (its tool
  result is the result JSON, or the validation message for a call the schema rejects, counted
  the same [R43], `SPEC.md` Recovery, forks, and replay) and recorded in State; otherwise its
  tool result is the `blocked lookup result` section, and nothing is counted or recorded. The
  loop goes on only while the last reply had tool calls and none was blocked. The Ollama client
  matches tool results to calls by order (T3 F3), so every tool call gets a result in order.
- The structured call sends the schema as Ollama's format over the whole history, with no
  tool bound. Both schemas require `confidence`, also on a question, because Ollama's
  enforcement of conditional schemas is untested; the program drops it on a question
  (`confidence` None [R48]). The guess-only schema has no `kind`.
- A guess, in Chinese or not, goes to F (a non-Chinese guess counts wrong there [R5]) and is
  written to the earlier guesses and questions; `owes` becomes "description". A valid question
  counts one question, is written there with `confidence` None, and goes to G; `owes` becomes
  "answer". An invalid question (Chinese, a card English name, or a distractor English name)
  repeats the structured call only, on the history plus the invalid reply as the model's
  message and the fixed message after it, with the attempt number one higher; the third
  invalid question is a Guesser violation and goes to F. Invalid questions never reach the
  earlier guesses and questions. The tool loop does not run on a retry.
- Attempt numbers [R26]: the tool-loop calls and the structured call of one try share one
  number, 1 on the first try (G zeroes the [R17] count), one more per retry.
- The lookup record, one entry per lookup run, in order: the round, the ordinal of the
  tool-loop call in this round (`call`, so several lookups from one reply can be told apart
  from several calls), the call's arguments as the model sent them, the result (the result
  JSON as the model read it, or the validation message), the tool result's status, and the
  tool-loop call's latency, token counts, and attempt number. Lookups of one reply share that
  reply's latency and tokens; `call` says so. A tool-loop reply without a tool call leaves no
  entry; its latency and tokens are only on the wrapper's Reply (M3 traces every call)."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from dont_say_oyster.corpus import CorpusEntry
from dont_say_oyster.llm import ClientFor, ModelSettings, call_structured, call_tools, ollama_client
from dont_say_oyster.oracle import check_question
from dont_say_oyster.search import search_tool
from dont_say_oyster.state import EarlierGuessOrQuestion, GuessOrQuestion, State, card_from_state

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "guesser.txt"

LOOKUP_LIMIT = 5  # per round [R43]
INVALID_QUESTION_LIMIT = 3  # the third invalid question is a violation [R17]
NONE = "(none)"

QUESTION_OR_GUESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["kind", "text", "confidence"],
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["question", "guess"]},
        "text": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

GUESS_ONLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["text", "confidence"],
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def sections(path: Path = PROMPT_PATH) -> dict[str, str]:
    """The prompt file's `=== name ===` sections, each stripped of surrounding blank lines."""
    found: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("=== ") and line.rstrip().endswith(" ==="):
            if name is not None:
                found[name] = "\n".join(lines).strip("\n")
            name = line.strip()[4:-4]
            lines = []
        else:
            lines.append(line)
    if name is not None:
        found[name] = "\n".join(lines).strip("\n")
    return found


def _earlier_texts(state: State) -> str:
    """The earlier descriptions and answers, without this round's item (the last entry when it
    is the one in the Guesser's row)."""
    texts = list(state["earlier_texts"])
    current = state["guesser_input"]
    if (
        texts
        and current is not None
        and texts[-1]["round"] == state["round"]
        and texts[-1]["kind"] == current["kind"]
        and texts[-1]["text"] == current["text"]
    ):
        texts.pop()
    return "\n".join(f"Round {t['round']} ({t['kind']}): {t['text']}" for t in texts) or NONE


def _earlier_guesses(state: State) -> str:
    lines = []
    for item in state["earlier_guesses"]:
        if item["kind"] == "guess":
            lines.append(
                f"Round {item['round']} (guess, confidence {item['confidence']}): {item['text']}"
            )
        else:
            lines.append(f"Round {item['round']} (question): {item['text']}")
    return "\n".join(lines) or NONE


def build_prompt(state: State) -> str:
    """The Guesser's prompt for this round, from the `prompt` section and the task section
    matching the schema (guess only when G set the flag [R16])."""
    texts = sections()
    task = texts["task: guess only"] if state["guess_only"] else texts["task: question or guess"]
    current = state["guesser_input"]
    slots = {
        "{round}": str(state["round"]),
        "{question_counter}": str(state["questions"]),
        "{earlier_descriptions_and_answers}": _earlier_texts(state),
        "{earlier_guesses_and_questions}": _earlier_guesses(state),
        "{description_or_answer}": current["text"] if current is not None else NONE,
        "{task}": task,
    }
    prompt = texts["prompt"]
    for slot, value in slots.items():
        prompt = prompt.replace(slot, value)
    return prompt


def _tool_loop(
    state: State,
    settings: ModelSettings,
    corpus: Sequence[CorpusEntry],
    client_for: ClientFor,
    messages: list[BaseMessage],
    attempt: int,
) -> tuple[int, list[dict[str, Any]]]:
    """Run the tool loop [R43] on `messages`, appending each reply and its tool results; return
    this round's lookup counter and the lookups appended to State's record."""
    tool = search_tool(corpus)
    blocked_text = sections()["blocked lookup result"]
    count = state["lookup_count"]
    lookups: list[dict[str, Any]] = []
    call_index = 0
    while True:
        call_index += 1
        reply = call_tools(settings, messages, [tool], attempt, client_for)
        messages.append(reply.output)
        blocked = False
        for call in reply.output.tool_calls:
            call_id = call["id"] or ""
            if blocked or count >= LOOKUP_LIMIT:
                messages.append(ToolMessage(blocked_text, tool_call_id=call_id))
                blocked = True
                continue
            result = tool.invoke(call)
            if not isinstance(result, ToolMessage):  # pragma: no cover - the tool's contract
                raise TypeError(f"search tool returned {type(result).__name__}")
            count += 1
            lookups.append({
                "round": state["round"],
                "call": call_index,
                "arguments": call["args"],
                "result": json.loads(result.text) if result.status == "success" else result.text,
                "status": result.status,
                "latency": reply.latency,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "attempt": reply.attempt,
            })
            messages.append(result)
        if not reply.output.tool_calls or blocked:
            return count, lookups


def node_e(
    state: State,
    settings: ModelSettings,
    corpus: Sequence[CorpusEntry],
    client_for: ClientFor = ollama_client,
) -> State:
    """E: the tool loop, then the structured call for a question or a guess, repeated with the
    fixed message on an invalid question [R17]; writes the Guesser's output, the lookups, the
    counters, `owes`, and on the third invalid question `violation`."""
    texts = sections()
    messages: list[BaseMessage] = [HumanMessage(build_prompt(state))]
    invalid = state["invalid_questions"]
    attempt = invalid + 1
    lookup_count, lookups = _tool_loop(state, settings, corpus, client_for, messages, attempt)
    after_loop: State = {
        **state,
        "lookup_count": lookup_count,
        "lookups": [*state["lookups"], *lookups],
    }
    schema = GUESS_ONLY_SCHEMA if state["guess_only"] else QUESTION_OR_GUESS_SCHEMA
    card = card_from_state(state)
    while True:
        reply = call_structured(settings, messages, schema, attempt, client_for)
        kind: Literal["guess", "question"] = (
            "guess" if state["guess_only"] or reply.output["kind"] == "guess" else "question"
        )
        text = str(reply.output["text"])
        output: GuessOrQuestion = {
            "kind": kind,
            "text": text,
            "confidence": float(reply.output["confidence"]) if kind == "guess" else None,
            "latency": reply.latency,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "attempt": reply.attempt,
        }
        remembered: EarlierGuessOrQuestion = {
            "round": state["round"],
            "kind": kind,
            "text": text,
            "confidence": output["confidence"],
        }
        if kind == "guess":
            return {
                **after_loop,
                "guesser_output": output,
                "earlier_guesses": [*state["earlier_guesses"], remembered],
                "invalid_questions": invalid,
                "owes": "description",
            }
        if not check_question(text, card, corpus).invalid:
            return {
                **after_loop,
                "guesser_output": output,
                "earlier_guesses": [*state["earlier_guesses"], remembered],
                "questions": state["questions"] + 1,
                "invalid_questions": invalid,
                "owes": "answer",
            }
        invalid += 1
        if invalid >= INVALID_QUESTION_LIMIT:
            return {
                **after_loop,
                "guesser_output": output,
                "invalid_questions": invalid,
                "violation": "Guesser",
            }
        messages.append(AIMessage(json.dumps(reply.output, ensure_ascii=False)))
        messages.append(HumanMessage(texts["fixed message [R17]"]))
        attempt += 1


def route_after_e(state: State) -> Literal["G", "F"]:
    """E's route: F on a guess or a Guesser violation, otherwise G for a new round after a
    valid question."""
    output = state["guesser_output"]
    if state["violation"] == "Guesser" or (output is not None and output["kind"] == "guess"):
        return "F"
    return "G"
