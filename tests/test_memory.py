"""The cross-game memory files and the two cross-game memory rows of State (SPEC.md Cross-game
memory definition: Storage, the size limit, each batch starts from empty memory)."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, load_cards
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.memory import (
    SCHEMA_PATH,
    Memory,
    MemoryFileError,
    advance,
    empty_memory,
    memory_path,
    read_memory,
    render,
    write_memory,
)
from dont_say_oyster.state import PROGRAM_ONLY, initial_state

FIVE: Memory = {
    "entries": [
        {"game": 1, "text": "E-one"},
        {"game": 2, "text": "E-two"},
        {"game": 4, "text": "E-four"},  # game 3 left no entry
        {"game": 5, "text": "E-five"},
        {"game": 6, "text": "E-six"},
    ],
    "summary": "S-summary",
}


def _raw(directory: Path, name: str, data: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(data), encoding="utf-8")


def test_game_1_reads_the_empty_memory_with_no_file_present(tmp_path: Path) -> None:
    directory = tmp_path / "not-created"
    assert read_memory(directory, "describer", 1) == empty_memory()
    assert read_memory(directory, "guesser", 1) == {"entries": [], "summary": None}
    assert not directory.exists()


def test_a_game_3_file_is_read_back_by_game_4_unchanged(tmp_path: Path) -> None:
    memory: Memory = {"entries": [{"game": 2, "text": "烤 entry"}, {"game": 3, "text": "E"}],
                      "summary": None}
    directory = tmp_path / "batch"
    path = write_memory(directory, "guesser", 3, memory)
    assert path == directory / "guesser-03.json"
    assert read_memory(directory, "guesser", 4) == memory


def test_the_file_names_carry_the_role_and_two_digit_game() -> None:
    assert memory_path(Path("d"), "describer", 7) == Path("d") / "describer-07.json"
    assert memory_path(Path("d"), "guesser", 40) == Path("d") / "guesser-40.json"


def test_game_4_with_no_game_3_file_raises_naming_the_path(tmp_path: Path) -> None:
    write_memory(tmp_path, "describer", 2, empty_memory())  # an older file is not read
    write_memory(tmp_path, "guesser", 3, empty_memory())  # nor the other role's
    with pytest.raises(MemoryFileError, match="describer-03.json"):
        read_memory(tmp_path, "describer", 4)


def test_a_written_file_validates_against_the_schema(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for memory in (empty_memory(), FIVE):
        path = write_memory(tmp_path, "describer", 6, memory)
        data = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(data, schema, cls=jsonschema.Draft202012Validator)
        assert data == {"role": "describer", "game": 6, **memory}


VALID = {"role": "describer", "game": 3, "entries": [{"game": 3, "text": "E"}], "summary": None}


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({k: v for k, v in VALID.items() if k != "summary"}, id="missing summary"),
        pytest.param({k: v for k, v in VALID.items() if k != "entries"}, id="missing entries"),
        pytest.param({**VALID, "entries": [{"game": 3}]}, id="entry missing text"),
        pytest.param({**VALID, "extra": 1}, id="unknown field"),
        pytest.param({**VALID, "role": "guesser"}, id="another role"),
        pytest.param({**VALID, "game": 2}, id="another game"),
        pytest.param(
            {**VALID, "entries": [{"game": 3, "text": "E"}, {"game": 2, "text": "E"}]},
            id="entries out of order",
        ),
    ],
)
def test_an_invalid_previous_file_raises_naming_the_path(
    tmp_path: Path, data: dict[str, Any]
) -> None:
    _raw(tmp_path, "describer-03.json", data)
    with pytest.raises(MemoryFileError, match="describer-03.json"):
        read_memory(tmp_path, "describer", 4)


def test_a_previous_file_with_six_entries_raises_naming_the_path(tmp_path: Path) -> None:
    """The file is game 6's and read by game 7, so only the entry count is wrong."""
    six = {"role": "describer", "game": 6,
           "entries": [{"game": g, "text": "E"} for g in range(1, 7)], "summary": None}
    _raw(tmp_path, "describer-06.json", six)
    with pytest.raises(MemoryFileError, match="describer-06.json"):
        read_memory(tmp_path, "describer", 7)


def test_a_file_that_is_not_json_raises(tmp_path: Path) -> None:
    (tmp_path / "describer-03.json").write_text("{", encoding="utf-8")
    with pytest.raises(MemoryFileError, match="describer-03.json"):
        read_memory(tmp_path, "describer", 4)


def test_a_file_that_is_not_utf8_raises(tmp_path: Path) -> None:
    (tmp_path / "describer-01.json").write_bytes(b"\xff\xfe")
    with pytest.raises(MemoryFileError, match="describer-01.json"):
        read_memory(tmp_path, "describer", 2)


def test_write_refuses_six_entries_and_writes_nothing(tmp_path: Path) -> None:
    six: Memory = {"entries": [{"game": g, "text": "E"} for g in range(1, 7)], "summary": None}
    with pytest.raises(MemoryFileError, match="describer-06.json"):
        write_memory(tmp_path, "describer", 6, six)
    assert not (tmp_path / "describer-06.json").exists()


def test_advance_on_five_entries_drops_the_oldest_and_keeps_five_in_order() -> None:
    after = advance(FIVE, 7, "E-seven", None)
    assert [e["game"] for e in after["entries"]] == [2, 4, 5, 6, 7]
    assert after["entries"][-1] == {"game": 7, "text": "E-seven"}
    assert after["summary"] == "S-summary"  # kept when none is given
    assert len(FIVE["entries"]) == 5  # the input is not changed


def test_advance_replaces_the_summary_when_given() -> None:
    assert advance(FIVE, 7, "E-seven", "S-new")["summary"] == "S-new"
    assert advance(empty_memory(), 1, "E-one", None) == {
        "entries": [{"game": 1, "text": "E-one"}], "summary": None,
    }


def test_advance_refuses_a_game_not_after_the_last_entry() -> None:
    with pytest.raises(ValueError, match="game 6"):
        advance(FIVE, 6, "E", None)


def test_render_shows_each_entry_with_its_game_number_once_and_the_summary_once() -> None:
    block = render(FIVE)
    for entry in FIVE["entries"]:
        assert block.count(f"Game {entry['game']}: {entry['text']}") == 1
        assert block.count(entry["text"]) == 1
    assert block.count("S-summary") == 1
    assert block.index("E-six") < block.index("S-summary")
    assert "(none)" not in block


def test_render_of_the_empty_memory_shows_none_for_both_parts() -> None:
    block = render(empty_memory())
    assert block.count("(none)") == 2
    assert "Game" not in block


def test_initial_state_holds_the_two_memory_rows_and_the_game() -> None:
    corpus = load_corpus(REPO_ROOT / "data" / "corpus" / "corpus.json")
    card = load_cards(CARDS_PATH, corpus)[0]
    start = initial_state(card)
    assert start["describer_memory"] == empty_memory()
    assert start["guesser_memory"] == empty_memory()
    assert start["game"] == 1
    later = initial_state(card, FIVE, empty_memory(), 7)
    assert (later["describer_memory"], later["guesser_memory"], later["game"]) == (
        FIVE, empty_memory(), 7,
    )
    assert "game" in PROGRAM_ONLY
    assert not {"describer_memory", "guesser_memory"} & PROGRAM_ONLY
