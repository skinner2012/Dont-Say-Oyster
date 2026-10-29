"""Whole games through the `play-game` command on the committed card 烤蚵仔 and the committed
corpus, with one scripted model per role injected through `main(argv, client_for=...)`: V2 games
for the loops, and one V0 and one V1 game for the toggles (no D node; no tool loop in V0); the
recursion limit and its arithmetic; the settings the command builds; the errors; `--help`. Every
test traces into memory (`in_memory_tracing`): none reads the developer's Langfuse keys or reaches
the stack. A game run through the command is read from its record, which every read validates
against the schema; a program-only or card field the record does not hold is read from the final
State of the same script run through `graph.play_game` directly (`play_directly`)."""

import json
import logging
import tomllib
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from jsonschema import Draft202012Validator
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from dont_say_oyster import describer, guesser, play, tracing
from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, Card, load_cards
from dont_say_oyster.challenger import REJECT_LIMIT
from dont_say_oyster.corpus import CorpusEntry, load_corpus
from dont_say_oyster.graph import (
    RECURSION_LIMIT,
    TOGGLES,
    WORST_CASE_STEPS,
    RoleSettings,
    Variant,
    build_graph,
    play_game,
)
from dont_say_oyster.guesser import INVALID_QUESTION_LIMIT, PROMPT_PATH
from dont_say_oyster.llm import ModelSettings, call_structured, call_text
from dont_say_oyster.play import (
    CORPUS_PATH,
    KEEP_ALIVE_CHALLENGER,
    KEEP_ALIVE_RESIDENT,
    main,
    role_settings,
)
from dont_say_oyster.program_nodes import SEND_BACKS, node_a
from dont_say_oyster.prompt_sections import sections
from dont_say_oyster.record import SCHEMA_PATH
from dont_say_oyster.state import PROGRAM_ONLY, ROUNDS, State
from dont_say_oyster.tracing import TracingClient
from tests.spans import METADATA, OBSERVATION_TYPE, metadata, of_type
from tests.test_guesser import tool_reply
from tests.test_llm import Scripted, raising, reply, scripted

CARD_ID = "card-5ed17f8f"  # 烤蚵仔
CLEAN = (
    "A street-stall snack of shellfish cooked over hot coals until the edges curl. "
    "It is topped with garlic, chili, and a splash of soy sauce paste."
)
CLEAN_2 = "Plump shellfish cooked over a flame until they pop open, served with a squeeze of lime."
CLEAN_3 = "Opened over heat and eaten hot from the half casing with garlic and chili on top."
CHINESE = "A night-market snack (夜市) of shellfish cooked over hot coals until the edges curl."
FORBIDDEN = "It is a grilled oyster from a night-market stall."  # oyster and grilled [R21]
ANSWER = "Yes, it is eaten hot, straight off the heat."
FAIL_REASON = "The detail of a batter coating also fits a fried oyster fritter."
INVALID = "Is it like an oyster omelet?"  # 蚵仔煎 is a distractor; its English names include it
VALID = "Is it eaten with a dipping sauce?"
WRONG = "蚵仔煎"
RIGHT = "烤牡蠣"  # an alias
ROLES = ("Describer", "Challenger", "Guesser")


# Scripted replies, one builder per kind of call.


def text(content: str) -> AIMessage:
    """A Describer reply."""
    return reply(content, 900, 60)


def verdict(value: str, reason: str = "") -> AIMessage:
    """A Challenger reply."""
    return reply(json.dumps({"verdict": value, "reason": reason}), 400, 20)


def no_tool_calls() -> AIMessage:
    """A Guesser tool-loop reply that makes no tool call, so the loop ends."""
    return reply("", 300, 20)


def guess(content: str) -> AIMessage:
    return reply(
        json.dumps({"kind": "guess", "text": content, "confidence": 0.8}, ensure_ascii=False),
        400,
        15,
    )


def question(content: str) -> AIMessage:
    return reply(json.dumps({"kind": "question", "text": content, "confidence": 0.5}), 400, 15)


def guesser_turn(*structured: AIMessage) -> list[AIMessage]:
    """One visit of E: the tool-loop reply, then the structured replies of its tries."""
    return [no_tool_calls(), *structured]


class Models:
    """One scripted model per role, handed out by `settings.role`; keeps the settings asked
    for."""

    def __init__(
        self,
        describer: Sequence[AIMessage] = (),
        challenger: Sequence[AIMessage] = (),
        guesser: Sequence[AIMessage] = (),
        challenger_model: Scripted | None = None,
    ) -> None:
        self.models: dict[str, Scripted] = {
            "Describer": scripted(*describer),
            "Challenger": challenger_model or scripted(*challenger),
            "Guesser": scripted(*guesser),
        }
        self.settings: dict[str, list[ModelSettings]] = {role: [] for role in ROLES}

    def __call__(self, settings: ModelSettings) -> Scripted:
        self.settings[settings.role].append(settings)
        return self.models[settings.role]

    def calls(self, role: str) -> int:
        """How many requests the role's model received."""
        return len(self.models[role].requests)


def run(
    tmp_path: Path, models: Models, *extra: str, card_id: str = CARD_ID, variant: str = "V2"
) -> tuple[int, Path]:
    """Run the command on `card_id` with `models` in `variant`; return the exit code and the
    output path."""
    output = tmp_path / "game.jsonl"
    code = main([card_id, str(output), "--variant", variant, *extra], client_for=models)
    return code, output


RECORD_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def game_record(output: Path) -> dict[str, Any]:
    """The record of the one game written to `output`: the file is one line, which validates
    against `data/records/schema.json`."""
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    RECORD_VALIDATOR.validate(record)
    assert isinstance(record, dict)
    return record


def play_directly(
    models: Models, variant: Variant = "V2", tracer: TracingClient | None = None
) -> State:
    """The final State of a game on `CARD_ID` run through `graph.play_game` directly, with the
    settings the command builds by default: for the program-only and card fields the record
    does not hold. Given `tracer`, the caller opens the game span, as `play.main` does."""
    corpus = load_corpus(CORPUS_PATH)
    cards = load_cards(CARDS_PATH, corpus)
    args = play.build_parser().parse_args([CARD_ID, "out.jsonl", "--variant", variant])
    return play_game(CARD_ID, cards, corpus, role_settings(args), models, tracer, TOGGLES[variant])


def in_memory_client() -> tuple[TracingClient, InMemorySpanExporter]:
    """A Langfuse client that exports into memory, under a public key of its own: the SDK's
    client registry is process-wide and keyed by public key, so each client gets a fresh key
    and its handler finds it there."""
    exporter = InMemorySpanExporter()
    public_key = f"pk-test-{uuid4().hex}"
    client = Langfuse(
        public_key=public_key,
        secret_key="sk-test",
        base_url="http://127.0.0.1:9",  # never reached: the exporter is in memory
        span_exporter=exporter,
    )
    return TracingClient(client, public_key), exporter


@pytest.fixture(autouse=True)
def in_memory_tracing(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    """Every command run in this module traces into memory: `tracing.build_client` never reads
    the developer's keys or reaches `localhost:3000`."""
    client, exporter = in_memory_client()
    monkeypatch.setattr(tracing, "build_client", lambda: client)
    return exporter


@pytest.fixture(scope="module")
def corpus() -> list[CorpusEntry]:
    return load_corpus(CORPUS_PATH)


@pytest.fixture(scope="module")
def cards(corpus: list[CorpusEntry]) -> list[Card]:
    return load_cards(CARDS_PATH, corpus)


def assert_calls_are_the_requests_and_the_spans(
    calls: Sequence[Mapping[str, Any]], models: Models, exporter: InMemorySpanExporter
) -> None:
    """One wrapper call is one `calls` entry and one generation span: as many entries as the
    scripted models received requests, ordinals 1..n, and the same (round, role, attempt, kind)
    multiset as the exporter's generation spans."""
    assert len(calls) == sum(models.calls(role) for role in ROLES)
    assert [entry["ordinal"] for entry in calls] == list(range(1, len(calls) + 1))
    generations = of_type(list(exporter.get_finished_spans()), "generation")
    assert len(generations) == len(calls)
    assert Counter(
        (entry["round"], entry["role"], entry["attempt"], entry["kind"]) for entry in calls
    ) == Counter(
        tuple(metadata(span, name) for name in ("round", "role", "attempt", "kind"))
        for span in generations
    )


# Whole games.


def right_guess_in_round_1() -> Models:
    return Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )


def test_a_right_guess_in_round_1_wins_and_writes_the_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = right_guess_in_round_1()
    code, output = run(tmp_path, models)
    assert code == 0
    record = game_record(output)
    assert (record["result"], record["matched_name"], record["counters"]["rounds"]) == (
        "right guess", RIGHT, 1
    )
    assert (record["card_id"], record["official_name"], record["variant"]) == (
        CARD_ID, "烤蚵仔", "V2"
    )
    (entry,) = record["rounds"]
    assert (entry["owed"], entry["reached_text"]) == ("description", CLEAN)
    assert entry["guesser_output"] == {"kind": "guess", "text": RIGHT, "confidence": 0.8}
    line = capsys.readouterr().out.strip()
    assert line == "Guesser wins (right guess): round 1, questions 0, rejects 0, forced passes 0"
    assert [models.calls(role) for role in ROLES] == [1, 1, 2]
    # The final State the record was built from still holds the program-only fields.
    assert PROGRAM_ONLY <= play_directly(right_guess_in_round_1()).keys()


def mixed_game() -> Models:
    """Round 1: Chinese, sent back; clean, rejected; clean, passed; a valid question. Round 2:
    the answer, guessed wrong. Round 3: a description, guessed right."""
    return Models(
        describer=[text(CHINESE), text(CLEAN), text(CLEAN_2), text(ANSWER), text(CLEAN_3)],
        challenger=[verdict("fail", FAIL_REASON), verdict("pass"), verdict("pass")],
        guesser=[
            *guesser_turn(question(VALID)),  # round 1
            *guesser_turn(guess(WRONG)),  # round 2, on the answer
            *guesser_turn(guess(RIGHT)),  # round 3
        ],
    )


def test_a_game_through_send_back_reject_question_answer_and_wrong_guess(
    tmp_path: Path, in_memory_tracing: InMemorySpanExporter, capsys: pytest.CaptureFixture[str]
) -> None:
    models = mixed_game()
    code, output = run(tmp_path, models)
    assert code == 0
    record = game_record(output)  # one line, valid against the schema
    assert record["result"] == "right guess"
    assert record["counters"] == {"rounds": 3, "questions": 1, "forced_passes": 0}
    rounds = record["rounds"]
    assert [entry["round"] for entry in rounds] == [1, 2, 3]
    assert [r["rejected"] for r in rounds] == [
        [{"description": CLEAN, "reason": FAIL_REASON}], [], []
    ]
    assert [(r["owed"], r["reached_text"]) for r in rounds] == [
        ("description", CLEAN_2), ("answer", ANSWER), ("description", CLEAN_3)
    ]
    assert [r["guesser_output"] for r in rounds] == [
        {"kind": "question", "text": VALID, "confidence": None},
        {"kind": "guess", "text": WRONG, "confidence": 0.8},
        {"kind": "guess", "text": RIGHT, "confidence": 0.8},
    ]
    # The Challenger judged the two descriptions of round 1 and the one of round 3, never the
    # answer [R12].
    assert [models.calls(role) for role in ROLES] == [5, 3, 6]
    assert capsys.readouterr().out.strip() == (
        "Guesser wins (right guess): round 3, questions 1, rejects 1, forced passes 0"
    )
    # Every call kept as the game ran: round 1 is B (sent back), B, D (fail), B, D (pass), E's
    # tool-loop call and its question; round 2 is B's answer and E; round 3 is B, D, and E.
    assert len(record["calls"]) == 14
    assert_calls_are_the_requests_and_the_spans(record["calls"], models, in_memory_tracing)
    assert [(c["node"], c["round"], c["attempt"], c["kind"], c["call"]) for c in
            record["calls"]] == [
        ("B", 1, 1, "text", None), ("B", 1, 2, "text", None), ("D", 1, 1, "structured", None),
        ("B", 1, 1, "text", None), ("D", 1, 1, "structured", None), ("E", 1, 1, "tools", 1),
        ("E", 1, 1, "structured", None),
        ("B", 2, 1, "text", None), ("E", 2, 1, "tools", 1), ("E", 2, 1, "structured", None),
        ("B", 3, 1, "text", None), ("D", 3, 1, "structured", None), ("E", 3, 1, "tools", 1),
        ("E", 3, 1, "structured", None),
    ]
    assert [r["sent_back"] for r in rounds] == [
        [{"node": "C", "kind": "description", "text": CHINESE, "ordinal": 1,
          "reason": "Chinese characters", "replaced": False}],
        [],
        [],
    ]
    assert [r["verdicts"] for r in rounds] == [
        [{"verdict": "fail", "reason": FAIL_REASON, "ordinal": 3},
         {"verdict": "pass", "reason": None, "ordinal": 5}],
        [],
        [{"verdict": "pass", "reason": None, "ordinal": 12}],
    ]
    # The reject counter is this round's [R25], so zero at the end.
    assert play_directly(mixed_game())["rejects"] == 0


def test_a_forbidden_word_in_round_2_is_a_describer_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN), text(FORBIDDEN)],
        challenger=[verdict("pass")],
        guesser=guesser_turn(guess(WRONG)),
    )
    code, output = run(tmp_path, models)
    assert code == 0
    record = game_record(output)
    assert (record["result"], record["counters"]["rounds"]) == ("Describer violation", 2)
    assert [(r["reached_text"], r["violating_text"]) for r in record["rounds"]] == [
        (CLEAN, None), (None, FORBIDDEN)
    ]
    assert capsys.readouterr().out.startswith("Guesser wins (Describer violation): round 2")
    assert [models.calls(role) for role in ROLES] == [2, 1, 2]


def test_three_invalid_questions_are_a_guesser_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)],
        challenger=[verdict("pass")],
        guesser=guesser_turn(*[question(INVALID)] * INVALID_QUESTION_LIMIT),
    )
    code, output = run(tmp_path, models)
    assert code == 0
    record = game_record(output)
    assert (record["result"], record["counters"]["questions"]) == ("Guesser violation", 0)
    (entry,) = record["rounds"]
    assert (entry["guesser_output"], entry["violating_question"]) == (None, INVALID)
    assert [sent["text"] for sent in entry["sent_back"]] == [INVALID] * (
        INVALID_QUESTION_LIMIT - 1
    )
    assert capsys.readouterr().out.startswith("Guesser loses (Guesser violation): round 1")
    assert [models.calls(role) for role in ROLES] == [1, 1, 1 + INVALID_QUESTION_LIMIT]


def ten_wrong_guesses() -> Models:
    return Models(
        describer=[text(CLEAN)] * ROUNDS,
        challenger=[verdict("pass")] * ROUNDS,
        guesser=[m for _ in range(ROUNDS) for m in guesser_turn(guess(WRONG))],
    )


def test_ten_wrong_guesses_lose_in_round_10_with_no_eleventh_round(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = ten_wrong_guesses()
    code, output = run(tmp_path, models)
    assert code == 0
    record = game_record(output)
    assert (record["result"], record["counters"]["rounds"]) == ("wrong guess in round 10", ROUNDS)
    assert [r["round"] for r in record["rounds"]] == list(range(1, ROUNDS + 1))
    assert [
        (r["reached_text"], r["guesser_output"]["text"]) for r in record["rounds"]
    ] == [(CLEAN, WRONG)] * ROUNDS
    # Every scripted reply was used and none was asked for beyond them.
    assert [models.calls(role) for role in ROLES] == [ROUNDS, ROUNDS, 2 * ROUNDS]
    assert capsys.readouterr().out.strip() == (
        "Guesser loses (wrong guess in round 10): round 10, questions 0, rejects 0, "
        "forced passes 0"
    )
    assert play_directly(ten_wrong_guesses())["guess_only"] is True  # round 10 [R16]


# The toggles (SPEC.md Ablation Design): V0 and V1 games.

KIND = METADATA + "kind"  # JSON-encoded
SEARCH_SECTION = sections(PROMPT_PATH)["search"]


def span_names(exporter: InMemorySpanExporter) -> set[str]:
    return {span.name for span in exporter.get_finished_spans()}


def observation_types(exporter: InMemorySpanExporter) -> list[str]:
    return [str((s.attributes or {}).get(OBSERVATION_TYPE)) for s in exporter.get_finished_spans()]


def generation_kinds(exporter: InMemorySpanExporter) -> set[str]:
    """The `kind` of every generation span: text, structured, or tools."""
    return {
        json.loads(str(s.attributes[KIND]))
        for s in exporter.get_finished_spans()
        if s.attributes is not None and s.attributes.get(OBSERVATION_TYPE) == "generation"
    }


@pytest.fixture
def guesser_prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The prompt (the first message) of every structured call the Guesser made, in order."""
    prompts: list[str] = []

    def recording(settings: Any, messages: Any, *args: Any, **kwargs: Any) -> Any:
        prompts.append(messages[0].text)
        return call_structured(settings, messages, *args, **kwargs)

    monkeypatch.setattr(guesser, "call_structured", recording)
    return prompts


def v0_game() -> Models:
    return Models(
        describer=[text(CLEAN), text(ANSWER), text(CLEAN_2)],
        guesser=[question(VALID), guess(WRONG), guess(RIGHT)],
    )


def test_a_v0_game_has_no_challenger_no_tool_loop_and_no_search_text_in_the_prompt(
    tmp_path: Path,
    in_memory_tracing: InMemorySpanExporter,
    guesser_prompts: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Round 1: a description reaches the Guesser straight from C, which asks a question; round
    2: the answer, with no Challenger call [R12]; round 3: a description, guessed right. Every
    E visit is one structured call: no tool-loop reply is scripted."""
    models = v0_game()
    code, output = run(tmp_path, models, variant="V0")
    assert code == 0
    record = game_record(output)
    assert record["variant"] == "V0"
    assert (record["result"], record["counters"]) == (
        "right guess", {"rounds": 3, "questions": 1, "forced_passes": 0}
    )
    assert [models.calls(role) for role in ROLES] == [3, 0, 3]
    # C sent each description and the answer on to the Guesser.
    assert [(r["owed"], r["reached_text"]) for r in record["rounds"]] == [
        ("description", CLEAN), ("answer", ANSWER), ("description", CLEAN_2)
    ]
    for entry in record["rounds"]:
        assert (entry["rejected"], entry["verdicts"], entry["lookups"], entry["sent_back"]) == (
            [], [], [], []
        )
    # No D span, no tool span, no tool-bound generation span.
    names = span_names(in_memory_tracing)
    assert {"G", "B", "C", "E", "F"} <= names and "D" not in names
    assert "tool" not in observation_types(in_memory_tracing)
    assert generation_kinds(in_memory_tracing) == {"text", "structured"}
    assert_calls_are_the_requests_and_the_spans(record["calls"], models, in_memory_tracing)
    assert [(c["node"], c["kind"], c["call"]) for c in record["calls"]] == [
        ("B", "text", None), ("E", "structured", None)
    ] * 3
    # The prompt never mentions the catalogue or the search tool (Self-checks) and has no
    # unfilled slot.
    assert len(guesser_prompts) == 3
    for prompt in guesser_prompts:
        assert SEARCH_SECTION not in prompt
        assert "catalogue" not in prompt and "search" not in prompt
        assert "{" not in prompt and "}" not in prompt
    assert capsys.readouterr().out.strip() == (
        "Guesser wins (right guess): round 3, questions 1, rejects 0, forced passes 0"
    )
    # C filled the row the Guesser reads, and D, the reject counter, and the lookup counter
    # were never written.
    state = play_directly(v0_game(), "V0")
    assert state["guesser_input"] is not None
    assert (state["guesser_input"]["kind"], state["guesser_input"]["text"]) == (
        "description", CLEAN_2
    )
    assert (state["rejects"], state["verdict"], state["d_route"]) == (0, None, None)
    assert state["lookup_count"] == 0


@pytest.fixture
def describer_prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The prompt (the first message) of every call the Describer made, in order."""
    prompts: list[str] = []

    def recording(settings: Any, messages: Any, *args: Any, **kwargs: Any) -> Any:
        prompts.append(messages[0].text)
        return call_text(settings, messages, *args, **kwargs)

    monkeypatch.setattr(describer, "call_text", recording)
    return prompts


@pytest.mark.parametrize("variant", ["V0", "V1"])
def test_without_the_challenger_the_describer_is_never_told_about_rejects(
    tmp_path: Path,
    in_memory_tracing: InMemorySpanExporter,
    describer_prompts: list[str],
    variant: str,
) -> None:
    """Round 1: a description sent back once for Chinese, then a clean one, guessed wrong; round
    2: a description guessed right. With the Challenger off no Describer prompt mentions a
    reject or a verdict, and every slot is filled."""
    guesser_replies = [guess(WRONG), guess(RIGHT)]
    if variant == "V1":
        guesser_replies = [*guesser_turn(guess(WRONG)), *guesser_turn(guess(RIGHT))]
    models = Models(describer=[text(CHINESE), text(CLEAN), text(CLEAN_2)], guesser=guesser_replies)
    code, output = run(tmp_path, models, variant=variant)
    assert code == 0
    record = game_record(output)
    assert (record["result"], record["counters"]["rounds"]) == ("right guess", 2)
    assert len(describer_prompts) == 3
    for prompt in describer_prompts:
        assert "reject" not in prompt.lower() and "verdict" not in prompt.lower()
        assert "{" not in prompt and "}" not in prompt
        assert "Official name (Chinese): 烤蚵仔\n" in prompt


def test_with_the_challenger_on_the_describer_prompt_holds_the_challenger_text(
    tmp_path: Path, in_memory_tracing: InMemorySpanExporter, describer_prompts: list[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, _ = run(tmp_path, models, variant="V2")
    assert code == 0
    (prompt,) = describer_prompts
    describer_sections = sections(describer.PROMPT_PATH)
    assert describer_sections["challenger rules"] in prompt
    assert "The verdict on your most recent description:\n(none)\n" in prompt
    assert "{" not in prompt and "}" not in prompt


def v1_game() -> Models:
    return Models(
        describer=[text(CLEAN)],
        guesser=[tool_reply({"keywords": ["oyster"]}), *guesser_turn(guess(RIGHT))],
    )


def test_a_v1_game_has_no_challenger_but_a_tool_loop_with_the_search_text_in_the_prompt(
    tmp_path: Path,
    in_memory_tracing: InMemorySpanExporter,
    guesser_prompts: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    models = v1_game()
    code, output = run(tmp_path, models, variant="V1")
    assert code == 0
    record = game_record(output)
    assert record["variant"] == "V1"
    assert (record["result"], record["counters"]) == (
        "right guess", {"rounds": 1, "questions": 0, "forced_passes": 0}
    )
    assert [models.calls(role) for role in ROLES] == [1, 0, 3]
    (entry,) = record["rounds"]
    assert entry["reached_text"] == CLEAN
    assert (entry["rejected"], entry["verdicts"], entry["sent_back"]) == ([], [], [])
    assert [(lookup["call"], lookup["status"]) for lookup in entry["lookups"]] == [
        (1, "success")
    ]
    names = span_names(in_memory_tracing)
    assert {"G", "B", "C", "E", "F", "search"} <= names and "D" not in names
    assert observation_types(in_memory_tracing).count("tool") == 1
    assert generation_kinds(in_memory_tracing) == {"text", "tools", "structured"}
    assert_calls_are_the_requests_and_the_spans(record["calls"], models, in_memory_tracing)
    assert [(c["node"], c["kind"], c["call"]) for c in record["calls"]] == [
        ("B", "text", None), ("E", "tools", 1), ("E", "tools", 2), ("E", "structured", None)
    ]
    (prompt,) = guesser_prompts
    assert SEARCH_SECTION in prompt
    assert "{" not in prompt and "}" not in prompt
    assert capsys.readouterr().out.strip() == (
        "Guesser wins (right guess): round 1, questions 0, rejects 0, forced passes 0"
    )
    # C filled the row the Guesser reads; D and the reject counter were never written.
    state = play_directly(v1_game(), "V1")
    assert state["guesser_input"] is not None
    assert (state["guesser_input"]["kind"], state["guesser_input"]["text"]) == (
        "description", CLEAN
    )
    assert (state["rejects"], state["verdict"], state["d_route"]) == (0, None, None)


@pytest.mark.parametrize("argv", [[], ["--variant", "V3"]], ids=["no-variant", "V3"])
def test_no_variant_or_v3_exits_non_zero_before_any_model_call(
    tmp_path: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    output = tmp_path / "game.jsonl"
    with pytest.raises(SystemExit) as exit_info:
        main([CARD_ID, str(output), *argv], client_for=models)
    assert exit_info.value.code != 0
    assert "--variant" in capsys.readouterr().err
    assert not output.exists()
    assert [models.calls(role) for role in ROLES] == [0, 0, 0]
    assert models.settings == {role: [] for role in ROLES}


# The recursion limit.


def worst_case() -> Models:
    """The scripted worst case: in each of ten rounds, three descriptions each sent back twice,
    two rejects then a forced pass, and a wrong guess, preceded in rounds 1–9 by two invalid
    questions."""
    descriptions_per_round = REJECT_LIMIT + 1
    describer = [
        m
        for _ in range(ROUNDS)
        for _ in range(descriptions_per_round)
        for m in [*[text(CHINESE)] * SEND_BACKS, text(CLEAN)]
    ]
    challenger = [verdict("fail", FAIL_REASON)] * (ROUNDS * descriptions_per_round)
    guesser = [
        m
        for round_ in range(1, ROUNDS + 1)
        for m in guesser_turn(
            *([question(INVALID)] * (INVALID_QUESTION_LIMIT - 1) if round_ < ROUNDS else []),
            guess(WRONG),
        )
    ]
    return Models(describer=describer, challenger=challenger, guesser=guesser)


def assert_worst_case_outcome(state: State) -> None:
    assert (state["result"], state["round"]) == ("wrong guess in round 10", ROUNDS)
    assert state["forced_passes"] == ROUNDS
    assert len(state["rejected"]) == ROUNDS * REJECT_LIMIT
    assert state["rejects"] == REJECT_LIMIT
    assert state["questions"] == 0
    assert len(state["earlier_guesses"]) == ROUNDS


def test_the_worst_case_game_reaches_f_without_hitting_the_recursion_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_tracing: InMemorySpanExporter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configs: list[Any] = []
    real_invoke = CompiledStateGraph.invoke

    def spy(self: Any, input: Any, config: Any = None, **kwargs: Any) -> Any:
        configs.append(config)
        return real_invoke(self, input, config, **kwargs)

    monkeypatch.setattr(CompiledStateGraph, "invoke", spy)
    models = worst_case()
    code, output = run(tmp_path, models)
    assert code == 0
    record = game_record(output)
    assert (record["result"], record["counters"]) == (
        "wrong guess in round 10", {"rounds": ROUNDS, "questions": 0, "forced_passes": ROUNDS}
    )
    rounds = record["rounds"]
    assert [len(r["rejected"]) for r in rounds] == [REJECT_LIMIT] * ROUNDS
    assert [r["guesser_output"]["text"] for r in rounds] == [WRONG] * ROUNDS
    # The one invoke: the limit, and the tracing handler the game's config carries.
    (config,) = configs
    assert set(config) == {"recursion_limit", "callbacks"}
    assert config["recursion_limit"] == RECURSION_LIMIT
    assert [type(h).__name__ for h in config["callbacks"]] == ["LangchainCallbackHandler"]
    assert all(isinstance(h, BaseCallbackHandler) for h in config["callbacks"])
    assert [models.calls(role) for role in ROLES] == [
        ROUNDS * (REJECT_LIMIT + 1) * (SEND_BACKS + 1),
        ROUNDS * (REJECT_LIMIT + 1),
        ROUNDS * (1 + INVALID_QUESTION_LIMIT) - (INVALID_QUESTION_LIMIT - 1),
    ]
    assert capsys.readouterr().out.strip() == (
        "Guesser loses (wrong guess in round 10): round 10, questions 0, rejects 20, "
        "forced passes 10"
    )
    calls = record["calls"]
    assert_calls_are_the_requests_and_the_spans(calls, models, in_memory_tracing)
    assert len(calls) == 158  # 90 Describer, 30 Challenger, 38 Guesser
    # The sent-back outputs: each description's two Chinese replies [R11] (the third reply of
    # each is clean), and in rounds 1–9 the two invalid questions before the guess [R17].
    sent_back = [{"round": r["round"], **entry} for r in rounds for entry in r["sent_back"]]
    by_node = Counter(entry["node"] for entry in sent_back)
    assert by_node == {"C": ROUNDS * (REJECT_LIMIT + 1) * SEND_BACKS,
                       "E": (ROUNDS - 1) * (INVALID_QUESTION_LIMIT - 1)}
    ordinals = {c["ordinal"]: c for c in calls}
    for entry in sent_back:
        made = ordinals[entry["ordinal"]]
        assert (made["node"], made["round"]) == ({"C": "B", "E": "E"}[entry["node"]],
                                                 entry["round"])
        if entry["node"] == "C":
            assert (entry["kind"], entry["text"], entry["reason"]) == (
                "description", CHINESE, "Chinese characters"
            )
        else:
            assert (entry["kind"], entry["text"], made["kind"]) == (
                "question", INVALID, "structured"
            )
            assert entry["reason"] == "the distractors' English names: Oyster Omelet (蚵仔煎)"
    assert [entry["round"] for entry in sent_back if entry["node"] == "E"] == [
        r for r in range(1, ROUNDS) for _ in range(INVALID_QUESTION_LIMIT - 1)
    ]
    # Every verdict: two rejects and the forced pass in each round, each with its reason, at
    # the ordinal of the Challenger call that gave it.
    verdicts = [{"round": r["round"], **entry} for r in rounds for entry in r["verdicts"]]
    assert [(v["round"], v["verdict"], v["reason"]) for v in verdicts] == [
        (r, "fail", FAIL_REASON) for r in range(1, ROUNDS + 1) for _ in range(REJECT_LIMIT + 1)
    ]
    assert [v["ordinal"] for v in verdicts] == [c["ordinal"] for c in calls if c["node"] == "D"]


def test_the_worst_case_arithmetic_is_exact(cards: list[Card], corpus: list[CorpusEntry]) -> None:
    """The worst-case game makes exactly WORST_CASE_STEPS node visits: LangGraph needs the
    limit above the visit count, so the limit at the count fails and one above passes."""
    assert RECURSION_LIMIT > WORST_CASE_STEPS
    assert WORST_CASE_STEPS == 240
    settings = role_settings(
        play.build_parser().parse_args([CARD_ID, "out.json", "--variant", "V2"])
    )
    (card,) = [c for c in cards if c.card_id == CARD_ID]
    with pytest.raises(GraphRecursionError):
        build_graph(settings, corpus, worst_case()).invoke(
            node_a(CARD_ID, [card]), RunnableConfig(recursion_limit=WORST_CASE_STEPS)
        )
    state = build_graph(settings, corpus, worst_case()).invoke(
        node_a(CARD_ID, [card]), RunnableConfig(recursion_limit=WORST_CASE_STEPS + 1)
    )
    assert_worst_case_outcome(cast(State, state))
    # The final State, its three lists at their longest, is still JSON.
    assert json.loads(json.dumps(state, ensure_ascii=False)) == state


# Errors.


def test_a_challenger_connection_error_in_round_2_exits_non_zero_without_an_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def replies() -> Iterator[AIMessage]:
        yield verdict("pass")
        raise httpx.ConnectError("[Errno 61] Connection refused")

    models = Models(
        describer=[text(CLEAN), text(CLEAN_2)],
        challenger_model=Scripted(messages=replies(), requests=[]),
        guesser=[*guesser_turn(guess(WRONG)), *guesser_turn(guess(RIGHT))],
    )
    code, output = run(tmp_path, models)
    assert code != 0
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Challenger" in captured.err and "Connection refused" in captured.err
    assert [models.calls(role) for role in ROLES] == [2, 2, 2]


@pytest.mark.parametrize("role", ["Describer", "Guesser"])
def test_a_describer_or_guesser_connection_error_exits_non_zero_without_an_output_file(
    role: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    models.models[role] = raising(httpx.ConnectError("[Errno 61] Connection refused"))
    code, output = run(tmp_path, models)
    assert code != 0
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert role in captured.err and "Connection refused" in captured.err
    assert models.calls(role) == 1  # the one request that failed; nothing is retried


def test_an_unknown_card_id_exits_non_zero_before_any_model_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, output = run(tmp_path, models, card_id="card-00000000")
    assert code != 0
    assert not output.exists()
    assert "card-00000000" in capsys.readouterr().err
    assert [models.calls(role) for role in ROLES] == [0, 0, 0]
    assert models.settings == {role: [] for role in ROLES}


def test_node_a_raises_on_an_unknown_card_id_before_the_graph_runs(
    cards: list[Card], corpus: list[CorpusEntry]
) -> None:
    settings = role_settings(
        play.build_parser().parse_args([CARD_ID, "out.json", "--variant", "V2"])
    )
    models = Models()
    with pytest.raises(KeyError, match="card-00000000"):
        play_game("card-00000000", cards, corpus, settings, models)
    assert [models.calls(role) for role in ROLES] == [0, 0, 0]


def test_a_missing_cards_file_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run(tmp_path, Models(), "--cards", str(tmp_path / "missing.json"))
    assert code != 0 and not output.exists()
    assert "missing.json" in capsys.readouterr().err


def test_a_missing_output_directory_is_created_and_the_file_written(tmp_path: Path) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    output = tmp_path / "runs" / "v2" / "game.jsonl"
    assert not output.parent.exists()
    code = main([CARD_ID, str(output), "--variant", "V2"], client_for=models)
    assert code == 0
    assert game_record(output)["result"] == "right guess"


def test_an_unwritable_output_path_exits_non_zero_before_any_model_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    output = blocker / "game.jsonl"  # the parent is a regular file
    code = main([CARD_ID, str(output), "--variant", "V2"], client_for=models)
    assert code != 0
    assert "not-a-directory" in capsys.readouterr().err
    assert [models.calls(role) for role in ROLES] == [0, 0, 0]
    assert models.settings == {role: [] for role in ROLES}


# Settings and logging.


def test_the_default_settings_are_the_role_defaults_with_keep_alive_fixed_per_role(
    tmp_path: Path,
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, _ = run(tmp_path, models)
    assert code == 0
    assert {role: set(s) for role, s in models.settings.items()} == {
        "Describer": {ModelSettings("Describer", "qwen3.8:27b-q4_K_M", 8192, 0.7, False, -1)},
        "Challenger": {ModelSettings("Challenger", "gemma4:12b-it-q4_K_M", 4096, 0.7, False, 0)},
        "Guesser": {ModelSettings("Guesser", "gemma4:26b-a4b-it-q4_K_M", 16384, 0.7, False, -1)},
    }
    assert (KEEP_ALIVE_RESIDENT, KEEP_ALIVE_CHALLENGER) == (-1, 0)


def test_the_parameters_set_each_roles_model_num_ctx_temperature_and_thinking() -> None:
    args = play.build_parser().parse_args([
        CARD_ID, "out.json", "--variant", "V2",
        "--describer-model", "qwen3.8:9b-q4_K_M", "--describer-num-ctx", "4096",
        "--challenger-model", "gemma4:4b-it-q4_K_M", "--challenger-num-ctx", "2048",
        "--guesser-model", "gemma4:12b-it-q4_K_M", "--guesser-num-ctx", "8192",
        "--temperature", "0.3",
        "--describer-thinking", "on", "--guesser-thinking", "on", "--challenger-thinking", "on",
    ])
    settings = role_settings(args)
    assert settings == RoleSettings(
        describer=ModelSettings("Describer", "qwen3.8:9b-q4_K_M", 4096, 0.3, "medium", -1),
        challenger=ModelSettings("Challenger", "gemma4:4b-it-q4_K_M", 2048, 0.3, True, 0),
        guesser=ModelSettings("Guesser", "gemma4:12b-it-q4_K_M", 8192, 0.3, True, -1),
    )


def test_thinking_on_is_a_level_for_qwen_and_true_for_gemma() -> None:
    assert play.thinking("qwen3.8:27b-q4_K_M", on=True) == "medium"
    assert play.thinking("gemma4:26b-a4b-it-q4_K_M", on=True) is True
    assert play.thinking("qwen3.8:27b-q4_K_M", on=False) is False
    assert play.thinking("gemma4:12b-it-q4_K_M", on=False) is False


def test_the_command_configures_logging_so_num_ctx_warnings_appear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    configured: list[dict[str, Any]] = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: configured.append(kw))
    models = Models(
        describer=[reply(CLEAN, 7500, 60)],  # over 90% of the Describer's num_ctx 8192
        challenger=[verdict("pass")],
        guesser=guesser_turn(guess(RIGHT)),
    )
    with caplog.at_level(logging.WARNING):
        code, _ = run(tmp_path, models)
    assert code == 0
    assert len(configured) == 1 and configured[0]["level"] == logging.WARNING
    # The program's warnings only: the Langfuse handler also warns once per model call that it
    # cannot read a model name off the scripted fake, which a ChatOllama has.
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name.startswith("dont_say_oyster")
    ]
    assert warnings == ["Describer: prompt tokens 7500 are over 90% of num_ctx 8192"]


# The command's interface.


def test_help_lists_every_parameter(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for parameter in (
        "card_id",
        "output",
        "--variant {V0,V1,V2}",
        "--cards",
        "--corpus",
        "--describer-model",
        "--describer-num-ctx",
        "--describer-thinking",
        "--challenger-model",
        "--challenger-num-ctx",
        "--challenger-thinking",
        "--guesser-model",
        "--guesser-num-ctx",
        "--guesser-thinking",
        "--temperature",
    ):
        assert parameter in out
    for absent in ("--memory", "keep-alive", "keep_alive"):
        assert absent not in out


def test_play_game_is_a_console_script() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["play-game"] == "dont_say_oyster.play:main"
