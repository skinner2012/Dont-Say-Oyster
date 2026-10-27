"""One scripted game is one trace (M3 T2): the spans a game exports through an in-memory
exporter, counted by name and type, with the session id and the trace name on every one; the
game span ended in error after a model error, the spans before it still exported; the session
id from the output path; and `build_client` with a variable missing, which returns None after
one warning, so the game runs untraced. No test needs the stack or Ollama."""

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from dont_say_oyster import tracing
from dont_say_oyster.play import main
from dont_say_oyster.tracing import NODE_A_SPAN, VARIABLES, TracingClient, session_id
from tests.test_guesser import tool_reply
from tests.test_llm import Scripted
from tests.test_play import (
    ANSWER,
    CARD_ID,
    CLEAN,
    CLEAN_2,
    RIGHT,
    ROLES,
    VALID,
    WRONG,
    Models,
    final_state,
    guess,
    guesser_turn,
    in_memory_client,
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


def run_traced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, models: Models
) -> tuple[int, Path, list[ReadableSpan]]:
    """Run the command into `tmp_path / SESSION / game.json` with an in-memory client; return
    the exit code, the output path, and the exported spans."""
    client, exporter = in_memory_client()
    monkeypatch.setattr(tracing, "build_client", lambda: client)
    output = tmp_path / SESSION / "game.json"
    code = main([CARD_ID, str(output)], client_for=models)
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
        code = main([CARD_ID, str(output)], client_for=models)
    return code, output, built


def test_without_keys_the_game_runs_untraced_after_one_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Both keys absent, the base URL present: no client, one warning naming both keys, and the
    game ends with its result in the output file (T2, Q2)."""
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
    (T2 audit F1), one warning saying so, and the game ends with its result in the output
    file."""
    environment(monkeypatch, "LANGFUSE_BASE_URL")
    code, output, built = run_with_the_real_build_client(tmp_path, monkeypatch, caplog)
    assert code == 0
    assert final_state(output)["result"] == "right guess"
    assert built == [None]
    assert tracing_warnings(caplog) == [
        "LANGFUSE_BASE_URL not set: the game runs untraced (with no base URL the SDK would fall "
        "back to Langfuse Cloud)"
    ]
