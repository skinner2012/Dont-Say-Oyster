"""Node B, the Describer (Full flow of one game), and its prompt builder. B makes one plain-text
call [R31], [R32] and writes the reply into the description or answer row, whichever `owes`
names [R10], [R29], with its latency, token counts, and attempt number [R26].

The prompt is the author's file `prompts/describer.txt`, read by its `=== name ===` sections:
the `prompt` section, with `{task}` replaced by the `task: description` or `task: answer`
section, and the `fixed message [R11]` section. The `conventions` section is for the
implementer and never goes to the model.

Ticket-level readings (T9, settled with the author through the M2 orchestrator, 2026-10-21):
- The prompt holds only the Describer's items of Information isolation, without cross-game
  memory (M6): the card's names, English names, and forbidden words; the round counter; earlier
  descriptions and answers; earlier guesses and questions, without the latest when it is the
  last entry; the latest guess or question; the latest verdict, only while this round's reject
  counter is above zero, so a verdict left from an earlier round is not shown; and the rejected
  descriptions with their reasons. A guess is shown without its confidence.
- On a send-back [R11] the request is the prompt, then the Describer's previous reply as the
  model's message, then the fixed message, so the model sees what it wrote; only the last reply
  is shown, not every reply sent back for this output.
- The attempt number is the [R11] count + 1 [R26]; G and D zero the count when they ask for a
  new output, so B only reads it."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from dont_say_oyster import prompt_sections
from dont_say_oyster.cards import REPO_ROOT
from dont_say_oyster.llm import ClientFor, ModelSettings, call_text, ollama_client
from dont_say_oyster.state import (
    Answer,
    Description,
    EarlierGuessOrQuestion,
    EarlierText,
    RejectedDescription,
    State,
    describer_output,
)

PROMPT_PATH = REPO_ROOT / "prompts" / "describer.txt"
NONE = "(none)"

def _list(items: Sequence[str]) -> str:
    return ", ".join(items) if items else NONE


def _lines(lines: Sequence[str]) -> str:
    return "\n".join(lines) if lines else NONE


def _earlier(item: EarlierText | EarlierGuessOrQuestion) -> str:
    return f"Round {item['round']}, {item['kind']}: {item['text']}"


def _rejected(item: RejectedDescription) -> str:
    return f"Round {item['round']}: {item['description']}\nReason: {item['reason']}"


def build_prompt(state: State, sections: dict[str, str]) -> str:
    """The Describer's prompt for the output `owes` names, from the Describer's items in State
    alone (Information isolation)."""
    official_name, *aliases = state["names"]
    latest = state["guesser_output"]
    earlier = state["earlier_guesses"]
    if (
        latest is not None
        and earlier
        and (earlier[-1]["kind"], earlier[-1]["text"]) == (latest["kind"], latest["text"])
    ):
        earlier = earlier[:-1]
    verdict = state["verdict"] if state["rejects"] > 0 else None
    if verdict is None:
        latest_verdict = NONE
    elif verdict["reason"] is None:
        latest_verdict = verdict["verdict"]
    else:
        latest_verdict = f"{verdict['verdict']}. Reason: {verdict['reason']}"
    return sections["prompt"].format_map({
        "official_name": official_name,
        "aliases": _list(aliases),
        "english_names": _list(state["english_names"]),
        "forbidden_words": _list(state["forbidden_words"]),
        "round": state["round"],
        "earlier_descriptions_and_answers": _lines(
            [_earlier(item) for item in state["earlier_texts"]]
        ),
        "earlier_guesses_and_questions": _lines([_earlier(item) for item in earlier]),
        "latest_guess_or_question": (
            NONE if latest is None else f"{latest['kind']}: {latest['text']}"
        ),
        "latest_verdict": latest_verdict,
        "rejected_descriptions": _lines([_rejected(item) for item in state["rejected"]]),
        "task": sections[f"task: {state['owes']}"],
    })


def build_messages(state: State, sections: dict[str, str]) -> list[BaseMessage]:
    """The request: the prompt alone on the first call; after a send-back [R11], the prompt, the
    previous reply, and the fixed message."""
    prompt = HumanMessage(build_prompt(state, sections))
    if state["describer_send_backs"] == 0:
        return [prompt]
    return [
        prompt,
        AIMessage(describer_output(state)),
        HumanMessage(sections["fixed message [R11]"]),
    ]


def node_b(
    state: State,
    settings: ModelSettings,
    client_for: ClientFor = ollama_client,
    sections: dict[str, str] | None = None,
) -> State:
    """B: one call for the description or answer `owes` names, written into its row as given."""
    sections = prompt_sections.sections(PROMPT_PATH) if sections is None else sections
    reply = call_text(
        settings,
        build_messages(state, sections),
        attempt=state["describer_send_backs"] + 1,
        client_for=client_for,
    )
    if state["owes"] == "answer":
        answer: Answer = {
            "answer": reply.output,
            "latency": reply.latency,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "attempt": reply.attempt,
        }
        return {**state, "answer": answer}
    description: Description = {
        "description": reply.output,
        "latency": reply.latency,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "attempt": reply.attempt,
    }
    return {**state, "description": description}
