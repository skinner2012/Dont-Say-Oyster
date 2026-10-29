"""The LangGraph State of one game: every row of the State schema except the two cross-game
memory rows (not built yet), the counters [R25], and the program-only fields the loops need. Every
value is a JSON type, so the final State can be written with `json.dumps`.

Readings settled with the author on 2026-10-20:
- The card's "Official name and accepted aliases" row is one list, `names`, official name
  first; whether a right guess matched the official name is `matched_name == names[0]`.
- "No result yet" is `result` None; otherwise it is one of the four F outcomes, and `winner`
  gives who won.
- A violation reaches F through the program-only `violation`, written by C (Describer) and E
  (Guesser), since only F writes the game result.
- There is no attempt-number field: each node computes the attempt number [R26] of its call from
  its own count (the [R11] count + 1, the [R17] count + 1, 2 for the [R40] re-ask).
- A token count [R26] is the pair `input_tokens`, `output_tokens` the wrapper reports.

The rows above keep latency, token counts, and attempt only for the last description, answer,
guess, and verdict and for each lookup, and B and E overwrite a sent-back output when its retry
arrives; so the per-call values (`SPEC.md` Metrics, Per model call) and what the program caught
(`SPEC.md` Implementation, Experiment result format) are appended by the nodes as the game runs,
into three program-only lists: `calls`, `sent_back`, and `verdicts`."""

from dataclasses import asdict
from typing import Any, Literal, TypedDict

from dont_say_oyster.cards import Card
from dont_say_oyster.corpus import Attributes
from dont_say_oyster.llm import CallKind, ModelSettings, Reply

ROUNDS = 10  # [R15]
QUESTION_LIMIT = 3  # [R16]

Outcome = Literal["right guess", "wrong guess in round 10", "Guesser violation",
                  "Describer violation"]
Winner = Literal["Guesser wins", "Guesser loses"]

_WINNER: dict[Outcome, Winner] = {
    "right guess": "Guesser wins",
    "wrong guess in round 10": "Guesser loses",
    "Guesser violation": "Guesser loses",
    "Describer violation": "Guesser wins",
}


class DescriptionOrAnswer(TypedDict):
    """The row the Guesser reads, filled by the program after C, or after D in V2–V3."""

    kind: Literal["description", "answer"]
    text: str
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


class Description(TypedDict):
    description: str
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


class Answer(TypedDict):
    answer: str
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


class GuessOrQuestion(TypedDict):
    """`confidence` is set on a guess and None on a question [R48]."""

    kind: Literal["guess", "question"]
    text: str
    confidence: float | None
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


class Verdict(TypedDict):
    """`reason` is None on a pass [R40]."""

    verdict: Literal["pass", "fail"]
    reason: str | None
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


class EarlierText(TypedDict):
    round: int
    kind: Literal["description", "answer"]
    text: str


class RejectedDescription(TypedDict):
    round: int
    description: str
    reason: str


class EarlierGuessOrQuestion(TypedDict):
    round: int
    kind: Literal["guess", "question"]
    text: str
    confidence: float | None


class Lookup(TypedDict):
    """One corpus lookup run by E: `name` and `arguments` as the model sent them,
    `result` the result JSON the model read, or the message it got for a call that was not
    searched (`status` "error")."""

    round: int
    call: int  # the index of the tool-loop call in the round (the `call` key of `Call`)
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | str
    status: str
    # These three are the tool-loop call's, and repeat across the lookups of one reply [R26].
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


CallNode = Literal["B", "D", "E"]


class Call(TypedDict):
    """One wrapper call (`SPEC.md` Metrics, Per model call), appended by the node that made it.
    `ordinal` is the entry's 1-based position in `calls`, since (round, role, attempt) alone is
    not unique [R26]; `call` is the round's tool-loop call index on a tool-bound call, the index
    its span and its `Lookup` entries carry, and None on any other call. A tool-bound call whose
    reply made several lookups is one entry."""

    ordinal: int
    node: CallNode
    role: str
    round: int
    attempt: int
    kind: CallKind
    call: int | None
    latency: float
    input_tokens: int | None
    output_tokens: int | None


CHINESE_CHARACTERS = "Chinese characters"  # why an output is sent back [R11], [R17], [R40]
EMPTY = "empty"  # why a fail reason is re-asked (an empty reason is re-asked like Chinese [R40])


class SentBack(TypedDict):
    """One output the program sent back (`SPEC.md` Implementation, Experiment result format): a
    description or answer with Chinese characters, by C [R11]; an invalid question, by E [R17];
    a fail reason re-asked, by D [R40]. `text` is the output as the model wrote it, `ordinal`
    the ordinal of the call that produced it, and `reason` why it was sent back. `replaced` is
    true only for the [R40] second reason that the fixed message replaced: it was not sent back,
    but it is kept because the record shows what validation caught. The last try that turns into
    a violation [R11], [R17] is not a send-back and has no entry."""

    round: int
    node: Literal["C", "D", "E"]
    kind: Literal["description", "answer", "question", "reason"]
    text: str
    ordinal: int
    reason: str
    replaced: bool


class VerdictEntry(TypedDict):
    """One D visit's verdict [R40]: `reason` as the verdict row shows it (None on a pass, the
    shown reason or the fixed message on a fail); `ordinal` that of the call that gave the
    verdict, the visit's first."""

    round: int
    verdict: Literal["pass", "fail"]
    reason: str | None
    ordinal: int


class State(TypedDict):
    # The card [R9]
    card_id: str
    names: list[str]  # official name, then the accepted aliases
    english_names: list[str]
    forbidden_words: list[str]
    attributes: dict[str, list[str]]
    distractors: list[str]

    # Model outputs and this game's history
    guesser_input: DescriptionOrAnswer | None
    description: Description | None
    answer: Answer | None
    guesser_output: GuessOrQuestion | None
    verdict: Verdict | None
    earlier_texts: list[EarlierText]  # earlier descriptions and answers
    rejected: list[RejectedDescription]
    earlier_guesses: list[EarlierGuessOrQuestion]  # guesses and valid questions [R17]
    lookups: list[Lookup]  # corpus lookup results

    # Counters [R25] and the game result
    round: int
    rejects: int  # this round
    lookup_count: int  # this round
    questions: int
    forced_passes: int
    result: Outcome | None

    # Program-only: not rows of the State schema
    violation: Literal["Describer", "Guesser"] | None
    matched_name: str | None  # the card name a right guess equals (Metrics)
    describer_send_backs: int  # [R11], for the output being asked for
    invalid_questions: int  # [R17], for the output being asked for
    reason_reasks: int  # [R40], for the verdict being asked for
    owes: Literal["description", "answer"]  # what the Describer is asked for [R10]
    guess_only: bool  # set by G [R16]
    d_route: Literal["B", "E"] | None  # D's route, written by D on every verdict [R13]
    calls: list[Call]  # every model call of the game, in order
    sent_back: list[SentBack]  # every output the program sent back, in order
    verdicts: list[VerdictEntry]  # every verdict of the game, in order


PROGRAM_ONLY = frozenset({
    "violation", "matched_name", "describer_send_backs", "invalid_questions", "reason_reasks",
    "owes", "guess_only", "d_route", "calls", "sent_back", "verdicts",
})


def with_call(
    calls: list[Call],
    node: CallNode,
    settings: ModelSettings,
    round_: int,
    reply: Reply[Any],
    call: int | None = None,
) -> list[Call]:
    """`calls` with one entry appended for the wrapper call that returned `reply`, its ordinal
    the next position; `call` is the tool-loop call index, given only on a tool-bound call."""
    return [
        *calls,
        {
            "ordinal": len(calls) + 1,
            "node": node,
            "role": settings.role,
            "round": round_,
            "attempt": reply.attempt,
            "kind": reply.kind,
            "call": call,
            "latency": reply.latency,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
        },
    ]


def winner(outcome: Outcome) -> Winner:
    """Who wins on each F outcome (Full flow of one game, the F row)."""
    return _WINNER[outcome]


def card_from_state(state: State) -> Card:
    """The card held in the State's card rows."""
    official_name, *aliases = state["names"]
    return Card(
        card_id=state["card_id"],
        official_name=official_name,
        aliases=tuple(aliases),
        english_names=tuple(state["english_names"]),
        forbidden_words=tuple(state["forbidden_words"]),
        attributes=Attributes(**{k: tuple(v) for k, v in state["attributes"].items()}),
        distractors=tuple(state["distractors"]),
    )


def describer_output(state: State) -> str:
    """The Describer's last reply for the output `owes` names. Raises ValueError when its row
    is empty."""
    if state["owes"] == "answer":
        answer = state["answer"]
        if answer is not None:
            return answer["answer"]
    else:
        description = state["description"]
        if description is not None:
            return description["description"]
    raise ValueError(f"no {state['owes']} from the Describer in round {state['round']}")


def initial_state(card: Card) -> State:
    """The State at game start: the card rows from `card`, no outputs, counters at zero."""
    return {
        "card_id": card.card_id,
        "names": [card.official_name, *card.aliases],
        "english_names": list(card.english_names),
        "forbidden_words": list(card.forbidden_words),
        "attributes": {k: list(v) for k, v in asdict(card.attributes).items()},
        "distractors": list(card.distractors),
        "guesser_input": None,
        "description": None,
        "answer": None,
        "guesser_output": None,
        "verdict": None,
        "earlier_texts": [],
        "rejected": [],
        "earlier_guesses": [],
        "lookups": [],
        "round": 0,
        "rejects": 0,
        "lookup_count": 0,
        "questions": 0,
        "forced_passes": 0,
        "result": None,
        "violation": None,
        "matched_name": None,
        "describer_send_backs": 0,
        "invalid_questions": 0,
        "reason_reasks": 0,
        "owes": "description",
        "guess_only": False,
        "d_route": None,
        "calls": [],
        "sent_back": [],
        "verdicts": [],
    }
