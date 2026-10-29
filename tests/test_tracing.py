"""One scripted game is one trace: the spans a game exports through an in-memory
exporter, counted by name and type, with the session id and the trace name on every one; the
game span ended in error after a model error, the spans before it still exported; the session
id from the output path; and `build_client` with a variable missing, which returns None after
one warning, so the game runs untraced. The per-call values on the spans: the role,
attempt, and kind on every generation span, with the token counts and the latency of the
wrapper's Reply; the round, call, and lookup on every tool span; and the events State does not
keep (send-backs, re-asks, a reply with no tool call), each as its own span. No test needs the
stack or Ollama."""

import json
import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from dont_say_oyster import challenger, describer, guesser, tracing
from dont_say_oyster.llm import Reply
from dont_say_oyster.play import main
from dont_say_oyster.tracing import NODE_A_SPAN, VARIABLES, TracingClient, session_id
from tests.test_guesser import tool_reply
from tests.test_llm import Scripted
from tests.test_play import (
    ANSWER,
    CARD_ID,
    CHINESE,
    CLEAN,
    CLEAN_2,
    INVALID,
    RIGHT,
    ROLES,
    VALID,
    WRONG,
    Models,
    final_state,
    guess,
    guesser_turn,
    in_memory_client,
    no_tool_calls,
    question,
    text,
    verdict,
)

SESSION = "t14"
PRESENT = {
    "LANGFUSE_PUBLIC_KEY": "pk-present",
    "LANGFUSE_SECRET_KEY": "sk-present",
    "LANGFUSE_BASE_URL": "http://127.0.0.1:9",  # never reached by any test
}
TRACING_LOGGER = "dont_say_oyster.tracing"
# The SDK's attribute keys, read off the exported spans of the smoke test, not from its code.
OBSERVATION_TYPE = "langfuse.observation.type"
SESSION_ID = "session.id"
TRACE_NAME = "langfuse.trace.name"
TRACE_METADATA_CARD_ID = "langfuse.trace.metadata.card_id"
METADATA = "langfuse.observation.metadata."  # + the run metadata key; values JSON-encoded
USAGE = "langfuse.observation.usage_details"  # JSON: {"input": n, "output": n, "total": n}
OUTPUT = "langfuse.observation.output"


def run_traced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, models: Models
) -> tuple[int, Path, list[ReadableSpan]]:
    """Run the command into `tmp_path / SESSION / game.json` with an in-memory client; return
    the exit code, the output path, and the exported spans."""
    client, exporter = in_memory_client()
    monkeypatch.setattr(tracing, "build_client", lambda: client)
    output = tmp_path / SESSION / "game.json"
    code = main([CARD_ID, str(output), "--variant", "V2"], client_for=models)
    return code, output, list(exporter.get_finished_spans())


def by_name(spans: list[ReadableSpan]) -> Counter[str]:
    return Counter(span.name for span in spans)


def of_type(spans: list[ReadableSpan], observation_type: str) -> list[ReadableSpan]:
    return [s for s in spans if attribute(s, OBSERVATION_TYPE) == observation_type]


def attribute(span: ReadableSpan, key: str) -> Any:
    return (span.attributes or {}).get(key)


def parent_name(span: ReadableSpan, spans: list[ReadableSpan]) -> str | None:
    if span.parent is None:
        return None
    (parent,) = [s for s in spans if s.context.span_id == span.parent.span_id]
    return parent.name


def test_a_scripted_game_is_one_trace_of_the_expected_spans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Round 1: a description, passed; the Guesser runs the search tool once with a valid query
    # (a keyword, see `SearchQuery` in search.py), then asks a valid question (E → G). Round 2:
    # the answer, no Challenger [R12]; the Guesser guesses right.
    models = Models(
        describer=[text(CLEAN), text(ANSWER)],
        challenger=[verdict("pass")],
        guesser=[
            tool_reply({"keywords": ["oyster"]}),
            *guesser_turn(question(VALID)),
            *guesser_turn(guess(RIGHT)),
        ],
    )
    code, output, spans = run_traced(tmp_path, monkeypatch, models)
    assert code == 0
    state = final_state(output)
    assert state["result"] == "right guess"
    assert [(lookup["round"], lookup["status"]) for lookup in state["lookups"]] == [
        (1, "success")
    ]
    assert [models.calls(role) for role in ROLES] == [2, 1, 5]

    names = by_name(spans)
    # One root span named by the card id, one A under it, one LangGraph chain span under it,
    # one chain span per node visit named by the node letter.
    assert names[CARD_ID] == 1 and names[NODE_A_SPAN] == 1 and names["LangGraph"] == 1
    assert {letter: names[letter] for letter in "GBCDEF"} == {
        "G": 2, "B": 2, "C": 2, "D": 1, "E": 2, "F": 1
    }
    (root,) = [s for s in spans if s.name == CARD_ID]
    assert root.parent is None
    (node_a,) = [s for s in spans if s.name == NODE_A_SPAN]
    (langgraph,) = [s for s in spans if s.name == "LangGraph"]
    assert parent_name(node_a, spans) == CARD_ID
    assert parent_name(langgraph, spans) == CARD_ID
    assert attribute(langgraph, OBSERVATION_TYPE) == "chain"
    node_spans = [s for s in spans if s.name in set("GBCDEF")]
    assert {attribute(s, OBSERVATION_TYPE) for s in node_spans} == {"chain"}
    assert {parent_name(s, spans) for s in node_spans} == {"LangGraph"}
    # One generation span per scripted model call, under the node that made it; one tool span
    # per scripted lookup.
    generations = of_type(spans, "generation")
    assert len(generations) == sum(models.calls(role) for role in ROLES)
    assert Counter(parent_name(s, spans) for s in generations) == {"B": 2, "D": 1, "E": 5}
    tools = of_type(spans, "tool")
    assert [(s.name, parent_name(s, spans)) for s in tools] == [("search", "E")]
    # One trace: the session id and the trace name on every span, the card id in the trace
    # metadata, and one trace id.
    assert {attribute(s, SESSION_ID) for s in spans} == {SESSION}
    assert {attribute(s, TRACE_NAME) for s in spans} == {CARD_ID}
    assert attribute(root, TRACE_METADATA_CARD_ID) == f'"{CARD_ID}"'
    assert {s.context.trace_id for s in spans} == {root.context.trace_id}
    assert root.status.status_code is StatusCode.UNSET


def test_a_model_error_ends_the_game_span_in_error_with_the_earlier_spans_exported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def replies() -> Any:
        yield verdict("pass")
        raise httpx.ConnectError("[Errno 61] Connection refused")

    models = Models(
        describer=[text(CLEAN), text(CLEAN_2)],
        challenger_model=Scripted(messages=replies(), requests=[]),
        guesser=[*guesser_turn(guess(WRONG)), *guesser_turn(guess(RIGHT))],
    )
    code, output, spans = run_traced(tmp_path, monkeypatch, models)
    assert code != 0 and not output.exists()
    assert "Connection refused" in capsys.readouterr().err
    (root,) = [s for s in spans if s.name == CARD_ID]
    assert root.status.status_code is StatusCode.ERROR
    assert "Connection refused" in (root.status.description or "")
    # Round 1 whole, round 2 up to the Challenger's failed call.
    names = by_name(spans)
    assert names[NODE_A_SPAN] == 1 and names["LangGraph"] == 1
    assert {letter: names[letter] for letter in "GBCDEF"} == {
        "G": 2, "B": 2, "C": 2, "D": 2, "E": 1, "F": 1
    }
    assert len(of_type(spans, "generation")) == sum(models.calls(role) for role in ROLES)
    assert {attribute(s, SESSION_ID) for s in spans} == {SESSION}
    assert {s.context.trace_id for s in spans} == {root.context.trace_id}


def test_the_session_id_is_the_resolved_parent_directory_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert session_id(tmp_path / "runs" / "t14" / "game.json") == "t14"
    monkeypatch.chdir(tmp_path)
    assert session_id(Path("out.json")) == tmp_path.resolve().name
    assert session_id(Path("out.json")) != ""


def environment(monkeypatch: pytest.MonkeyPatch, *missing: str) -> None:
    """`.env` not loaded; the three variables set to local test values except `missing`."""
    monkeypatch.setattr(tracing, "load_dotenv", lambda: None)
    for name, value in PRESENT.items():
        if name in missing:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)


def tracing_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == TRACING_LOGGER]


@pytest.mark.parametrize("missing", VARIABLES)
def test_build_client_returns_none_with_one_warning_naming_the_missing_variable(
    missing: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    environment(monkeypatch, missing)
    with caplog.at_level(logging.WARNING, logger=TRACING_LOGGER):
        assert tracing.build_client() is None
    (warning,) = tracing_warnings(caplog)
    assert warning.startswith(f"{missing} not set: the game runs untraced")
    assert ("Langfuse Cloud" in warning) == (missing == "LANGFUSE_BASE_URL")


def run_with_the_real_build_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> tuple[int, Path, list[TracingClient | None]]:
    """Run a one-round game through the real `build_client`, recording what it returned."""
    built: list[TracingClient | None] = []
    real_build_client = tracing.build_client

    def spy() -> TracingClient | None:
        built.append(real_build_client())
        return built[-1]

    monkeypatch.setattr(tracing, "build_client", spy)
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    output = tmp_path / SESSION / "game.json"
    with caplog.at_level(logging.WARNING, logger=TRACING_LOGGER):
        code = main([CARD_ID, str(output), "--variant", "V2"], client_for=models)
    return code, output, built


def test_without_keys_the_game_runs_untraced_after_one_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Both keys absent, the base URL present: no client, one warning naming both keys, and the
    game ends with its result in the output file (author, 2026-10-25)."""
    environment(monkeypatch, "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    code, output, built = run_with_the_real_build_client(tmp_path, monkeypatch, caplog)
    assert code == 0
    assert final_state(output)["result"] == "right guess"
    assert built == [None]
    assert tracing_warnings(caplog) == [
        "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY not set: the game runs untraced"
    ]


def test_without_a_base_url_the_game_runs_untraced_after_one_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Both keys present, the base URL absent: no client, so nothing could go to Langfuse Cloud
    (rejected, `docs/DECISIONS.md`, 2026-10-23), one warning saying so, and the game ends with its
    result in the output file."""
    environment(monkeypatch, "LANGFUSE_BASE_URL")
    code, output, built = run_with_the_real_build_client(tmp_path, monkeypatch, caplog)
    assert code == 0
    assert final_state(output)["result"] == "right guess"
    assert built == [None]
    assert tracing_warnings(caplog) == [
        "LANGFUSE_BASE_URL not set: the game runs untraced (with no base URL the SDK would fall "
        "back to Langfuse Cloud)"
    ]


# The per-call values on the spans.

CHINESE_REASON = "The batter (麵糊) also fits a fried oyster fritter."
ENGLISH_REASON = "The batter also fits a fried oyster fritter."
DELAY = 0.01  # every scripted reply, so a span's duration has something to match


def metadata(span: ReadableSpan, key: str) -> Any:
    """A run metadata value on `span`, decoded; None when the span does not carry it."""
    value = attribute(span, METADATA + key)
    return None if value is None else json.loads(value)


def key(span: ReadableSpan) -> tuple[Any, Any]:
    return metadata(span, "round"), metadata(span, "call")


def in_order(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    return sorted(spans, key=lambda s: s.start_time or 0)


class Replies:
    """Every Reply the wrapper returned in a game, in call order, with the role that made it:
    the wrapper functions are wrapped where the nodes look them up."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.replies: list[tuple[str, Reply[Any]]] = []
        for module, name in (
            (describer, "call_text"),
            (challenger, "call_structured"),
            (guesser, "call_tools"),
            (guesser, "call_structured"),
        ):
            monkeypatch.setattr(module, name, self.recording(getattr(module, name)))

    def recording(self, call: Callable[..., Reply[Any]]) -> Callable[..., Reply[Any]]:
        def recorded(settings: Any, *args: Any, **kwargs: Any) -> Reply[Any]:
            result = call(settings, *args, **kwargs)
            self.replies.append((settings.role, result))
            return result

        return recorded


class Game:
    """The traced game of `every_event_game`: its final State, its spans, and its Replies."""

    def __init__(
        self, state: Any, spans: list[ReadableSpan], replies: list[tuple[str, Reply[Any]]]
    ) -> None:
        self.state = state
        self.spans = spans
        self.replies = replies
        self.generations = in_order(of_type(spans, "generation"))
        self.tools = in_order(of_type(spans, "tool"))

    def generations_of(self, role: str) -> list[ReadableSpan]:
        return [s for s in self.generations if metadata(s, "role") == role]


@pytest.fixture
def every_event_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Game:
    """One scripted two-round game holding every kind of event the trace records.

    Round 1: a description with Chinese, sent back once [R11], then a clean one, which the
    Challenger fails with a Chinese reason and is re-asked for an English one [R40]; rejected,
    so a new description, passed. The Guesser's tool loop: call 1 carries two searches, a valid
    one (lookup 1) and one the schema rejects (lookup 2); call 2 names an unknown tool (lookup
    3); call 3 carries three searches, so lookups 4 and 5 run and the sixth is blocked [R43].
    The structured call asks an invalid question, re-asked once with the fixed message [R17],
    then a valid one. Round 2: the answer, no Challenger [R12]; the tool loop's one reply makes
    no tool call; the Guesser guesses right."""
    models = Models(
        describer=[text(CHINESE), text(CLEAN), text(CLEAN_2), text(ANSWER)],
        challenger=[
            verdict("fail", CHINESE_REASON), verdict("fail", ENGLISH_REASON), verdict("pass")
        ],
        guesser=[
            tool_reply({"keywords": ["oyster"]}, {"main_ingredients": ["Oysters"]}),
            tool_reply({"keywords": ["oyster"]}, name="lookup"),
            tool_reply({"keywords": ["squid"]}, {"keywords": ["snail"]}, {"keywords": ["omelet"]}),
            question(INVALID),
            question(VALID),
            no_tool_calls(),
            guess(RIGHT),
        ],
    )
    for model in models.models.values():
        model.delay = DELAY
    replies = Replies(monkeypatch)
    code, output, spans = run_traced(tmp_path, monkeypatch, models)
    assert code == 0
    state = final_state(output)
    assert (state["result"], state["round"], state["questions"]) == ("right guess", 2, 1)
    assert [models.calls(role) for role in ROLES] == [4, 3, 7]
    return Game(state, spans, replies.replies)


def test_every_generation_span_carries_its_role_attempt_kind_tokens_and_latency(
    every_event_game: Game,
) -> None:
    game = every_event_game
    assert len(game.generations) == len(game.replies) == 14
    for span, (role, result) in zip(game.generations, game.replies, strict=True):
        assert metadata(span, "role") == role
        assert metadata(span, "attempt") == result.attempt
        usage = json.loads(attribute(span, USAGE))
        assert (usage["input"], usage["output"]) == (result.input_tokens, result.output_tokens)
        assert span.start_time is not None and span.end_time is not None
        duration = (span.end_time - span.start_time) / 1e9
        # The span wraps the model's time: never shorter than the scripted reply's delay.
        assert duration >= DELAY
        assert abs(duration - result.latency) < 0.1
    # Every generation span says its round, from the script: round 1 has three B, three D,
    # three tool-bound E, and two structured E calls; round 2 has B's answer, E's tool-bound
    # call, and its guess.
    assert [metadata(s, "round") for s in game.generations] == [1] * 11 + [2] * 3
    assert [metadata(s, "kind") for s in game.generations] == [
        "text", "text", "structured", "structured", "text", "structured",  # round 1, B to D
        "tools", "tools", "tools", "structured", "structured",  # round 1, E
        "text", "tools", "structured",  # round 2
    ]


def test_a_description_sent_back_once_gives_two_b_generations_with_attempts_1_and_2(
    every_event_game: Game,
) -> None:
    describer_spans = every_event_game.generations_of("Describer")
    names = [parent_name(s, every_event_game.spans) for s in describer_spans]
    assert names == ["B"] * 4
    # The send-back [R11], then the new description after the reject [R13], then the answer.
    assert [metadata(s, "attempt") for s in describer_spans] == [1, 2, 1, 1]


def test_a_challenger_reask_gives_two_d_generations_with_attempts_1_and_2(
    every_event_game: Game,
) -> None:
    challenger_spans = every_event_game.generations_of("Challenger")
    assert [parent_name(s, every_event_game.spans) for s in challenger_spans] == ["D"] * 3
    # The re-ask [R40] in the first D visit; the second visit judges the new description.
    assert [metadata(s, "attempt") for s in challenger_spans] == [1, 2, 1]
    first, second, _ = challenger_spans
    assert first.parent is not None and second.parent is not None
    assert first.parent.span_id == second.parent.span_id
    assert every_event_game.state["rejected"][0]["reason"] == ENGLISH_REASON


def test_a_question_reasked_once_gives_two_structured_e_generations_with_attempts_1_and_2(
    every_event_game: Game,
) -> None:
    game = every_event_game
    guesser_spans = game.generations_of("Guesser")
    structured = [s for s in guesser_spans if metadata(s, "kind") == "structured"]
    # The re-ask [R17] in round 1, then round 2's guess.
    assert [(parent_name(s, game.spans), metadata(s, "attempt")) for s in structured] == [
        ("E", 1), ("E", 2), ("E", 1)
    ]
    # The tool-loop calls of round 1 share the first try's number [R26].
    tool_bound = [s for s in guesser_spans if metadata(s, "kind") == "tools"]
    assert [(key(s), metadata(s, "attempt")) for s in tool_bound] == [
        ((1, 1), 1), ((1, 2), 1), ((1, 3), 1), ((2, 1), 1)
    ]


def test_a_reply_with_two_tool_calls_gives_two_tool_spans_with_its_round_and_call(
    every_event_game: Game,
) -> None:
    game = every_event_game
    (generation,) = [s for s in game.generations if key(s) == (1, 1)]
    tools = [s for s in game.tools if key(s) == (1, 1)]
    assert [metadata(s, "lookup") for s in tools] == [1, 2]
    # Siblings under E's chain span, not children of the generation span.
    assert generation.parent is not None
    assert [s.parent.span_id if s.parent else None for s in tools] == [
        generation.parent.span_id
    ] * 2
    assert parent_name(generation, game.spans) == "E"
    # Each tool span names its Lookup entry: the round's entries in counter order.
    lookups = [entry for entry in game.state["lookups"] if entry["round"] == 1]
    for span in game.tools:
        entry = lookups[metadata(span, "lookup") - 1]
        assert (entry["round"], entry["call"]) == key(span)
        assert json.loads(attribute(span, "langfuse.observation.input")) == entry["arguments"]
    (valid, _) = tools
    assert json.loads(json.loads(attribute(valid, OUTPUT))["content"]) == lookups[0]["result"]


def test_a_call_the_schema_rejects_gives_a_tool_span_whose_output_is_the_validation_message(
    every_event_game: Game,
) -> None:
    game = every_event_game
    (span,) = [s for s in game.tools if metadata(s, "lookup") == 2]
    rejected = game.state["lookups"][1]
    assert rejected["status"] == "error" and isinstance(rejected["result"], str)
    assert rejected["result"].startswith("The search was not run; the tool's schema rejects")
    assert json.loads(attribute(span, OUTPUT))["content"] == rejected["result"]


def test_a_call_naming_an_unknown_tool_gives_a_generation_span_and_no_tool_span(
    every_event_game: Game,
) -> None:
    game = every_event_game
    assert game.state["lookups"][2]["name"] == "lookup"
    assert [key(s) for s in game.generations if key(s) == (1, 2)] == [(1, 2)]
    assert [s for s in game.tools if key(s) == (1, 2)] == []
    assert 3 not in [metadata(s, "lookup") for s in game.tools]


def test_the_sixth_lookup_gives_no_tool_span(every_event_game: Game) -> None:
    game = every_event_game
    # Call 3 carried three searches; the third was blocked [R43].
    (generation,) = [s for s in game.generations if key(s) == (1, 3)]
    assert len(json.loads(attribute(generation, OUTPUT))["tool_calls"]) == 3
    assert [metadata(s, "lookup") for s in game.tools if key(s) == (1, 3)] == [4, 5]
    assert game.state["lookup_count"] == 0  # G zeroed it for round 2
    assert len(game.state["lookups"]) == 5
    # Every search run is one tool span: lookups 1, 2, 4, 5 (3 named an unknown tool).
    assert [(key(s), metadata(s, "lookup")) for s in game.tools] == [
        ((1, 1), 1), ((1, 1), 2), ((1, 3), 4), ((1, 3), 5)
    ]


def test_a_tool_bound_reply_with_no_tool_call_gives_a_generation_span_and_no_tool_span(
    every_event_game: Game,
) -> None:
    game = every_event_game
    (generation,) = [s for s in game.generations if key(s) == (2, 1)]
    assert metadata(generation, "kind") == "tools"
    assert json.loads(attribute(generation, OUTPUT)).get("tool_calls") in (None, [])
    assert [s for s in game.tools if metadata(s, "round") == 2] == []
    assert [entry for entry in game.state["lookups"] if entry["round"] == 2] == []
