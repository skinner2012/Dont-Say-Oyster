"""The JSONL game record (`record.py`, `data/records/schema.json`): records built from the final
States of scripted games on the committed card 烤蚵仔, run through `graph.play_game` with the
settings the command builds, and records written by the command itself; every record validates
against the schema. The record's `memory` (V3): a written, a not-written, and a game-six case,
with scripted token counts. The schema itself: every object lists every one of its fields as
required and allows no other, except a lookup's arguments and result."""

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from dont_say_oyster import play, tracing
from dont_say_oyster.cards import CARDS_PATH, load_cards
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.graph import GameMemory, RoleSettings, Variant
from dont_say_oyster.llm import ModelSettings
from dont_say_oyster.memory import Memory, Role, read_memory, write_memory
from dont_say_oyster.play import CORPUS_PATH
from dont_say_oyster.program_nodes import SEND_BACKS
from dont_say_oyster.record import SCHEMA_PATH, build_record, write_record
from dont_say_oyster.state import HResult, State, initial_state
from tests.test_guesser import tool_reply
from tests.test_play import (
    ANSWER,
    CARD_ID,
    CHINESE,
    CLEAN,
    CLEAN_2,
    CLEAN_3,
    D_ENTRY,
    D_SUMMARY,
    FAIL_REASON,
    G_ENTRY,
    G_SUMMARY,
    INVALID,
    RIGHT,
    VALID,
    WRONG,
    Models,
    game_memory,
    game_record,
    guess,
    guesser_turn,
    h_reply,
    in_memory_client,
    mixed_replies,
    no_tool_calls,
    play_directly,
    question,
    run,
    text,
    v0_game,
    v3_game,
    verdict,
)

COUNTS: dict[Role, int] = {"describer": 11, "guesser": 13}
NAMING = "Grilled oysters sold at night markets: search for them first."  # an English name

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
FORBIDDEN_ANSWER = "Yes, it is a grilled oyster."  # oyster and grilled [R21]
LOOKUP_KEYS = ("call", "name", "arguments", "status", "result")


@pytest.fixture(autouse=True)
def in_memory_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every command run here traces into memory, never to the developer's stack."""
    client, _ = in_memory_client()
    monkeypatch.setattr(tracing, "build_client", lambda: client)


def default_settings(variant: Variant = "V2") -> RoleSettings:
    args = play.build_parser().parse_args([CARD_ID, "out.jsonl", "--variant", variant])
    return play.role_settings(args)


def played(
    models: Models,
    variant: Variant = "V2",
    memory: GameMemory | None = None,
    tokens: Mapping[Role, int] | None = None,
) -> tuple[State, dict[str, Any]]:
    """The final State of the scripted game and its record, which validates; a V3 game takes
    `memory` and the scripted token counts (`COUNTS` unless given)."""
    state = play_directly(models, variant, memory=memory)
    if memory is not None and tokens is None:
        tokens = COUNTS
    record = build_record(state, variant, default_settings(variant), tokens)
    VALIDATOR.validate(record)
    assert json.loads(json.dumps(record, ensure_ascii=False)) == record
    return state, record


def test_the_mixed_v2_game_has_each_round_with_its_own_events_and_states_calls() -> None:
    """Round 1: Chinese, sent back; clean, rejected; clean, passed; one lookup, then a valid
    question. Round 2: the answer, no lookup, a wrong guess. Round 3: a description, passed; one
    lookup, then the right guess."""
    models = Models(
        describer=[text(CHINESE), text(CLEAN), text(CLEAN_2), text(ANSWER), text(CLEAN_3)],
        challenger=[verdict("fail", FAIL_REASON), verdict("pass"), verdict("pass")],
        guesser=[
            tool_reply({"keywords": ["oyster"]}), no_tool_calls(), question(VALID),
            no_tool_calls(), guess(WRONG),
            tool_reply({"keywords": ["squid"]}), no_tool_calls(), guess(RIGHT),
        ],
    )
    state, record = played(models)
    assert (record["card_id"], record["official_name"], record["variant"]) == (
        CARD_ID, "烤蚵仔", "V2"
    )
    assert (record["result"], record["matched_name"]) == ("right guess", RIGHT)
    assert record["counters"] == {"rounds": 3, "questions": 1, "forced_passes": 0}
    first, second, third = record["rounds"]
    assert [r["round"] for r in record["rounds"]] == [1, 2, 3]
    assert [(r["owed"], r["reached_text"]) for r in record["rounds"]] == [
        ("description", CLEAN_2), ("answer", ANSWER), ("description", CLEAN_3)
    ]
    assert first["rejected"] == [{"description": CLEAN, "reason": FAIL_REASON}]
    assert first["sent_back"] == [
        {"node": "C", "kind": "description", "text": CHINESE, "ordinal": 1,
         "reason": "Chinese characters", "replaced": False}
    ]
    assert first["verdicts"] == [
        {"verdict": "fail", "reason": FAIL_REASON, "ordinal": 3},
        {"verdict": "pass", "reason": None, "ordinal": 5},
    ]
    assert third["verdicts"] == [{"verdict": "pass", "reason": None, "ordinal": 13}]
    assert [[(lk["call"], lk["arguments"]) for lk in r["lookups"]] for r in record["rounds"]] == [
        [(1, {"keywords": ["oyster"]})], [], [(1, {"keywords": ["squid"]})]
    ]
    for entry in (second, third):
        assert (entry["rejected"], entry["sent_back"]) == ([], [])
    assert second["verdicts"] == [] and second["lookups"] == []
    assert [r["guesser_output"] for r in record["rounds"]] == [
        {"kind": "question", "text": VALID, "confidence": None},
        {"kind": "guess", "text": WRONG, "confidence": 0.8},
        {"kind": "guess", "text": RIGHT, "confidence": 0.8},
    ]
    assert {(r["violating_question"], r["violating_text"]) for r in record["rounds"]} == {
        (None, None)
    }
    # Each round's items are State's, in order, without the round key.
    for entry in record["rounds"]:
        for name in ("rejected", "verdicts", "sent_back"):
            assert entry[name] == [
                {k: v for k, v in item.items() if k != "round"}
                for item in state[name]
                if item["round"] == entry["round"]
            ]
    assert record["calls"] == state["calls"]
    assert len(record["calls"]) == 16


def test_a_v0_game_has_no_verdict_and_no_lookup_in_any_round() -> None:
    _, record = played(v0_game(), "V0")
    assert (record["variant"], record["result"]) == ("V0", "right guess")
    assert len(record["rounds"]) == 3
    for entry in record["rounds"]:
        assert (entry["verdicts"], entry["lookups"], entry["rejected"]) == ([], [], [])
    assert {c["role"] for c in record["calls"]} == {"Describer", "Guesser"}


def test_a_v1_game_has_its_lookups_with_arguments_status_and_results() -> None:
    """Call 1 carries a valid search and one the schema rejects; call 2 names an unknown tool;
    call 3 makes no tool call."""
    models = Models(
        describer=[text(CLEAN)],
        guesser=[
            tool_reply({"keywords": ["oyster"]}, {"main_ingredients": ["Oysters"]}),
            tool_reply({"keywords": ["oyster"]}, name="lookup"),
            *guesser_turn(guess(RIGHT)),
        ],
    )
    state, record = played(models, "V1")
    (entry,) = record["rounds"]
    assert entry["verdicts"] == [] and entry["rejected"] == []
    lookups = entry["lookups"]
    assert [(lk["call"], lk["name"], lk["status"]) for lk in lookups] == [
        (1, "search", "success"), (1, "search", "error"), (2, "lookup", "error")
    ]
    assert [lk["arguments"] for lk in lookups] == [
        {"keywords": ["oyster"]}, {"main_ingredients": ["Oysters"]}, {"keywords": ["oyster"]}
    ]
    found, rejected, unknown = (lk["result"] for lk in lookups)
    assert isinstance(found, dict) and set(found) == {"results", "more_results"}
    assert any(hit["official_name"] == "烤蚵仔" for hit in found["results"])
    assert isinstance(rejected, str) and rejected.startswith("The search was not run")
    assert isinstance(unknown, str) and "lookup" in unknown
    # The lookups as State keeps them, without the call's metrics, which `calls` holds.
    assert lookups == [
        {k: lk[k] for k in LOOKUP_KEYS}  # type: ignore[literal-required]
        for lk in state["lookups"]
    ]
    assert all(set(lk) == set(LOOKUP_KEYS) for lk in lookups)


def test_a_describer_violation_in_an_answer_is_in_the_last_round_with_no_reached_text() -> None:
    """Round 1: a description, then a valid question; round 2: the answer names the card."""
    models = Models(
        describer=[text(CLEAN), text(FORBIDDEN_ANSWER)],
        challenger=[verdict("pass")],
        guesser=guesser_turn(question(VALID)),
    )
    _, record = played(models)
    assert (record["result"], record["counters"]["rounds"]) == ("Describer violation", 2)
    first, last = record["rounds"]
    assert (first["reached_text"], first["violating_text"]) == (CLEAN, None)
    assert (last["owed"], last["reached_text"], last["violating_text"]) == (
        "answer", None, FORBIDDEN_ANSWER
    )
    assert (last["guesser_output"], last["violating_question"]) == (None, None)


def test_a_third_chinese_reply_in_round_1_leaves_one_round_begun_and_no_text_reached() -> None:
    """[R11]: the first description of round 1 comes back with Chinese three times, so the round
    is begun but nothing reached the Guesser [R14]."""
    models = Models(describer=[text(CHINESE)] * (SEND_BACKS + 1))
    _, record = played(models)
    assert (record["result"], record["counters"]["rounds"]) == ("Describer violation", 1)
    (entry,) = record["rounds"]
    assert (entry["owed"], entry["reached_text"], entry["violating_text"]) == (
        "description", None, CHINESE
    )
    assert [sent["text"] for sent in entry["sent_back"]] == [CHINESE] * SEND_BACKS
    assert entry["verdicts"] == [] and entry["guesser_output"] is None


def test_a_guesser_violation_holds_the_violating_question_and_no_guesser_output() -> None:
    models = Models(
        describer=[text(CLEAN)],
        challenger=[verdict("pass")],
        guesser=guesser_turn(question(INVALID), question(INVALID), question(INVALID)),
    )
    _, record = played(models)
    assert record["result"] == "Guesser violation"
    (entry,) = record["rounds"]
    assert (entry["reached_text"], entry["guesser_output"], entry["violating_question"]) == (
        CLEAN, None, INVALID
    )
    assert entry["violating_text"] is None
    assert [sent["text"] for sent in entry["sent_back"]] == [INVALID, INVALID]


def test_the_rejected_descriptions_of_the_record_are_the_printed_rejects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round 1: three fails, the third a forced pass [R13], and a wrong guess; round 2: a fail,
    then a pass, and the right guess. The printed count is the whole game's rejects."""
    models = Models(
        describer=[text(CLEAN), text(CLEAN_2), text(CLEAN_3), text(CLEAN), text(CLEAN_2)],
        challenger=[
            *[verdict("fail", FAIL_REASON)] * 3, verdict("fail", FAIL_REASON), verdict("pass")
        ],
        guesser=[*guesser_turn(guess(WRONG)), *guesser_turn(guess(RIGHT))],
    )
    code, output = run(tmp_path, models)
    assert code == 0
    printed = re.search(r"rejects (\d+), forced passes (\d+)", capsys.readouterr().out)
    assert printed is not None
    record = game_record(output)
    assert sum(len(r["rejected"]) for r in record["rounds"]) == int(printed[1]) == 3
    assert record["counters"]["forced_passes"] == int(printed[2]) == 1
    assert [len(r["verdicts"]) for r in record["rounds"]] == [3, 2]


def test_two_runs_into_one_path_leave_two_lines_each_parseable_alone(tmp_path: Path) -> None:
    """A description with a newline in it is written escaped, so each record stays one line."""
    with_newline = "A street-stall snack of shellfish.\nIt is eaten hot from the coals."
    for _ in range(2):
        models = Models(
            describer=[text(with_newline)],
            challenger=[verdict("pass")],
            guesser=guesser_turn(guess(RIGHT)),
        )
        code, output = run(tmp_path, models)
        assert code == 0
    content = output.read_text(encoding="utf-8")
    assert content.count("\n") == 2 and content.endswith("\n")
    lines = content.splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        VALIDATOR.validate(record)
        assert record["rounds"][0]["reached_text"] == with_newline
        assert "烤蚵仔" in line  # Chinese written as it is, not escaped


def test_the_record_carries_the_settings_play_game_resolved(tmp_path: Path) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, output = run(
        tmp_path, models,
        "--describer-thinking", "on", "--guesser-model", "gemma4:12b-it-q4_K_M",
        "--guesser-num-ctx", "8192", "--temperature", "0.3",
    )
    assert code == 0
    assert game_record(output)["settings"] == {
        "describer": {"model": "qwen3.8:27b-q4_K_M", "num_ctx": 16384, "thinking": "medium",
                      "keep_alive": -1},
        "challenger": {"model": "gemma4:12b-it-q4_K_M", "num_ctx": 4096, "thinking": False,
                       "keep_alive": 0},
        "guesser": {"model": "gemma4:12b-it-q4_K_M", "num_ctx": 8192, "thinking": False,
                    "keep_alive": -1},
        "temperature": 0.3,
    }


def test_build_record_raises_when_the_roles_temperatures_differ() -> None:
    state = play_directly(v0_game(), "V0")
    settings = default_settings()

    def at(role: ModelSettings, temperature: float) -> ModelSettings:
        return ModelSettings(role.role, role.model, role.num_ctx, temperature, role.thinking,
                             role.keep_alive)

    mixed = RoleSettings(settings.describer, settings.challenger, at(settings.guesser, 0.3))
    with pytest.raises(ValueError, match="temperatures differ"):
        build_record(state, "V0", mixed)


def test_build_record_raises_for_a_game_with_no_result() -> None:
    corpus = load_corpus(CORPUS_PATH)
    (card,) = [c for c in load_cards(CARDS_PATH, corpus) if c.card_id == CARD_ID]
    with pytest.raises(ValueError, match="no result"):
        build_record(initial_state(card), "V2", default_settings())


# The record's memory (V3; SPEC.md Implementation, Experiment result format: the memory
# summary, each role's redo count, the memory token count).


def test_a_written_game_1_has_both_entries_no_summary_and_the_counts(tmp_path: Path) -> None:
    state, record = played(v3_game(), "V3", game_memory(tmp_path))
    assert record["variant"] == "V3"
    assert record["memory"] == {
        "game": 1,
        "describer": {"entry": D_ENTRY, "summary": None, "redos": 0, "written": True,
                      "failed": [], "tokens": 11},
        "guesser": {"entry": G_ENTRY, "summary": None, "redos": 0, "written": True,
                    "failed": [], "tokens": 13},
    }
    # The two role objects are State's H rows plus the count.
    rows: list[tuple[Role, HResult | None]] = [
        ("describer", state["describer_h"]), ("guesser", state["guesser_h"])
    ]
    for role, row in rows:
        assert row is not None
        assert record["memory"][role] == {**row, "tokens": COUNTS[role]}
    assert [c["node"] for c in record["calls"]][-2:] == ["H", "H"]


def test_a_game_not_written_for_the_guesser_has_its_three_failed_outputs(
    tmp_path: Path,
) -> None:
    """The Guesser's entry names an English name of the card three times: sent back twice,
    refused the third time, the previous memory copied forward (Cross-game memory definition,
    Check rule)."""
    models = v3_game(h_reply(NAMING), h_reply(NAMING), h_reply(NAMING))
    _, record = played(models, "V3", game_memory(tmp_path))
    guesser_calls = [c["ordinal"] for c in record["calls"] if c["node"] == "H"
                     and c["role"] == "Guesser"]
    assert len(guesser_calls) == 3
    assert record["memory"]["guesser"] == {
        "entry": None, "summary": None, "redos": 2, "written": False,
        "failed": [
            {"attempt": attempt, "ordinal": ordinal, "entry": NAMING, "summary": None,
             "reasons": ["the card's English names"]}
            for attempt, ordinal in zip((1, 2, 3), guesser_calls, strict=True)
        ],
        "tokens": 13,
    }
    assert record["memory"]["describer"]["written"] is True
    assert read_memory(tmp_path, "guesser", 2) == {"entries": [], "summary": None}


def test_a_game_6_has_the_summaries_and_the_count_of_game_5_s_rendering(tmp_path: Path) -> None:
    five: Memory = {
        "entries": [{"game": g, "text": f"entry {g}"} for g in range(1, 6)], "summary": None
    }
    write_memory(tmp_path, "describer", 5, five)
    write_memory(tmp_path, "guesser", 5, five)
    describer, challenger, guesser = mixed_replies()
    models = Models(
        describer=[*describer, h_reply(D_ENTRY, D_SUMMARY)],
        challenger=challenger,
        guesser=[*guesser, h_reply(G_ENTRY, G_SUMMARY)],
    )
    _, record = played(models, "V3", game_memory(tmp_path, 6), {"describer": 70, "guesser": 65})
    assert record["memory"] == {
        "game": 6,
        "describer": {"entry": D_ENTRY, "summary": D_SUMMARY, "redos": 0, "written": True,
                      "failed": [], "tokens": 70},
        "guesser": {"entry": G_ENTRY, "summary": G_SUMMARY, "redos": 0, "written": True,
                    "failed": [], "tokens": 65},
    }
    assert read_memory(tmp_path, "guesser", 7) == {
        "entries": [*five["entries"][1:], {"game": 6, "text": G_ENTRY}], "summary": G_SUMMARY
    }


def test_build_record_refuses_counts_that_disagree_with_the_variant(tmp_path: Path) -> None:
    state = play_directly(v3_game(), "V3", memory=game_memory(tmp_path))
    with pytest.raises(ValueError, match="plays with memory but no memory token counts"):
        build_record(state, "V3", default_settings("V3"))
    v2 = play_directly(v0_game(), "V0")
    with pytest.raises(ValueError, match="plays without memory but memory token counts"):
        build_record(v2, "V0", default_settings("V0"), COUNTS)
    # A V3 record needs H's rows: a State that never reached H has none.
    with pytest.raises(ValueError, match="H has not run"):
        build_record(v2, "V3", default_settings("V3"), COUNTS)


def test_write_record_creates_the_file_and_appends_one_line(tmp_path: Path) -> None:
    path = tmp_path / "game.jsonl"
    write_record({"a": "烤蚵仔\n"}, path)
    write_record({"b": 1}, path)
    assert path.read_text(encoding="utf-8") == '{"a": "烤蚵仔\\n"}\n{"b": 1}\n'


# The schema.


def object_schemas(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Every subschema of `node` that describes an object, with its path."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        types = node.get("type")
        if types == "object" or (isinstance(types, list) and "object" in types):
            found.append((path, node))
        for key, value in node.items():
            found.extend(object_schemas(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(object_schemas(value, f"{path}/{index}"))
    return found


def test_the_schema_requires_every_field_and_allows_no_other() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    open_objects = []
    for path, schema in object_schemas(SCHEMA):
        if "properties" not in schema:
            open_objects.append(path)
            continue
        assert schema.get("additionalProperties") is False, path
        assert sorted(schema["required"]) == sorted(schema["properties"]), path
    # The two exceptions: what the model sent and what the search tool returned.
    lookup = "/$defs/round/properties/lookups/items/properties"
    assert open_objects == [f"{lookup}/arguments", f"{lookup}/result"]
    # No conditional branches: a key that does not apply is null or an empty list.
    text = json.dumps(SCHEMA)
    for keyword in ('"if"', '"then"', '"else"', '"dependentRequired"', '"dependentSchemas"'):
        assert keyword not in text


@pytest.mark.parametrize(
    "change",
    ["missing top-level key", "extra top-level key", "missing round key", "extra round key",
     "extra call key", "extra settings key"],
)
def test_the_schema_rejects_a_record_with_a_missing_or_extra_field(change: str) -> None:
    _, record = played(v0_game(), "V0")
    entry = record["rounds"][0]
    if change == "missing top-level key":
        del record["settings"]
    elif change == "extra top-level key":
        record["memory_summary"] = ""
    elif change == "missing round key":
        del entry["violating_text"]
    elif change == "extra round key":
        entry["memory"] = None
    elif change == "extra call key":
        record["calls"][0]["thinking_tokens"] = 0
    else:
        record["settings"]["describer"]["temperature"] = 0.7
    with pytest.raises(ValidationError):
        VALIDATOR.validate(record)


@pytest.mark.parametrize(
    "change",
    ["missing memory key", "extra memory key", "missing role key", "extra role key",
     "extra failed key", "unknown reason"],
)
def test_the_schema_rejects_a_memory_object_with_a_missing_extra_or_unknown_field(
    change: str, tmp_path: Path
) -> None:
    models = v3_game(h_reply(NAMING), h_reply(G_ENTRY))
    _, record = played(models, "V3", game_memory(tmp_path))
    memory = record["memory"]
    if change == "missing memory key":
        del memory["game"]
    elif change == "extra memory key":
        memory["challenger"] = None
    elif change == "missing role key":
        del memory["describer"]["tokens"]
    elif change == "extra role key":
        memory["guesser"]["words"] = 12
    elif change == "extra failed key":
        memory["guesser"]["failed"][0]["round"] = 3
    else:
        memory["guesser"]["failed"][0]["reasons"] = ["an English name"]
    with pytest.raises(ValidationError):
        VALIDATOR.validate(record)
