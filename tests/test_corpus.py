"""Corpus loader: schema validation, the checks in code, typed entries, and the entry point."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dont_say_oyster.corpus import SCHEMA_PATH, Attributes, CorpusError, load_corpus, main

FIXTURES = Path(__file__).parent / "fixtures" / "corpus"
GOOD = FIXTURES / "good.json"


def test_schema_path_is_the_repo_schema() -> None:
    assert SCHEMA_PATH == Path(__file__).resolve().parents[1] / "data" / "corpus" / "schema.json"
    assert SCHEMA_PATH.is_file()


def test_good_fixture_loads_into_three_typed_entries() -> None:
    entries = load_corpus(GOOD)
    assert [e.official_name for e in entries] == ["蚵仔煎", "珍珠奶茶", "鳳梨酥"]
    oyster, tea, cake = entries
    assert oyster.aliases == ("蚵煎",)
    assert oyster.english_names[0] == "oyster omelette"
    assert "oyster" in oyster.forbidden_words
    assert oyster.attributes == Attributes(
        dish_type=("Snack",),
        main_ingredients=("Seafood", "Egg", "Starch"),
        cooking_method=("Pan-Fried",),
        flavor=("Savory", "Sweet"),
        physical_form=("Sauced",),
        occasion=("Night Market",),
    )
    assert tea.attributes.physical_form == ("Drink with Add-ins",)
    # Empty aliases and an empty optional attribute are allowed.
    assert cake.aliases == ()
    assert tea.attributes.occasion == ()


# fixture, the expected start of the one problem line (entry and field), and a word of the reason
BAD = [
    ("bad_unknown_field", "entry 1 (珍珠奶茶), field region:", "unknown field"),
    ("bad_unknown_attribute", "entry 2 (鳳梨酥), field attributes.texture:", "unknown field"),
    ("bad_missing_field", "entry 1, field official_name:", "missing field"),
    ("bad_missing_attribute", "entry 2 (鳳梨酥), field attributes.occasion:", "missing field"),
    ("bad_empty_official_name", "entry 0, field official_name:", "non-empty"),
    ("bad_empty_english_names", "entry 2 (鳳梨酥), field english_names:", "non-empty"),
    ("bad_value_not_allowed", "entry 0 (蚵仔煎), field attributes.flavor:", "'Umami'"),
    ("bad_too_many_values", "entry 0 (蚵仔煎), field attributes.cooking_method:", "too long"),
    ("bad_too_few_values", "entry 2 (鳳梨酥), field attributes.main_ingredients:", "non-empty"),
    ("bad_repeated_attribute_value", "entry 1 (珍珠奶茶), field attributes.flavor:", "non-unique"),
    ("bad_empty_list_string", "entry 0 (蚵仔煎), field aliases:", "non-empty"),
    ("bad_repeated_list_string", "entry 1 (珍珠奶茶), field forbidden_words:", "non-unique"),
    ("bad_wrong_type", "entry 0 (蚵仔煎), field aliases:", "not of type 'array'"),
    (
        "bad_attribute_not_array",
        "entry 2 (鳳梨酥), field attributes.physical_form:",
        "not of type 'array'",
    ),
    (
        "bad_drink_form_without_drink",
        "entry 2 (鳳梨酥), field attributes.physical_form:",
        "Dish type is not Drink",
    ),
    (
        "bad_drink_without_drink_form",
        "entry 1 (珍珠奶茶), field attributes.physical_form:",
        "Dish type is Drink",
    ),
    ("bad_duplicate_official_name", "entry 2 (蚵仔煎), field official_name:", "entry 0"),
    ("bad_alias_equals_official_name", "entry 1 (珍珠奶茶), field aliases:", "official name"),
    ("bad_alias_shared_across_entries", "entry 2 (鳳梨酥), field aliases:", "alias of entry 0"),
    (
        "bad_alias_is_other_official_name",
        "entry 2 (鳳梨酥), field aliases:",
        "official name of entry 1",
    ),
    (
        "bad_official_name_is_other_alias",
        "entry 2 (波霸奶茶), field official_name:",
        "alias of entry 1",
    ),
]


@pytest.mark.parametrize(("fixture", "where", "reason"), BAD, ids=[b[0] for b in BAD])
def test_bad_fixture_fails_naming_entry_and_field(fixture: str, where: str, reason: str) -> None:
    with pytest.raises(CorpusError) as info:
        load_corpus(FIXTURES / f"{fixture}.json")
    assert len(info.value.problems) == 1, info.value.problems
    problem = info.value.problems[0]
    assert problem.startswith(where), problem
    assert reason in problem, problem


def test_every_bad_fixture_is_tested() -> None:
    on_disk = {p.stem for p in FIXTURES.glob("bad_*.json")}
    tested = {b[0] for b in BAD} | {"bad_not_an_array", "bad_json_syntax"}
    assert on_disk == tested


def _write_good_with(tmp_path: Path, mutate: Callable[[list[dict[str, Any]]], None]) -> Path:
    corpus = json.loads(GOOD.read_text(encoding="utf-8"))
    mutate(corpus)
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    return path


def test_every_schema_problem_is_reported_in_entry_order(tmp_path: Path) -> None:
    def mutate(corpus: list[dict[str, Any]]) -> None:
        corpus[0]["english_names"] = []
        del corpus[2]["attributes"]["flavor"]
        del corpus[2]["attributes"]["occasion"]

    with pytest.raises(CorpusError) as info:
        load_corpus(_write_good_with(tmp_path, mutate))
    assert info.value.problems == [
        "entry 0 (蚵仔煎), field english_names: [] should be non-empty",
        "entry 2 (鳳梨酥), field attributes.flavor: missing field",
        "entry 2 (鳳梨酥), field attributes.occasion: missing field",
    ]


def test_name_checks_run_only_after_the_schema_passes(tmp_path: Path) -> None:
    def mutate(corpus: list[dict[str, Any]]) -> None:
        corpus[2]["official_name"] = "蚵仔煎"
        corpus[1]["region"] = "Taipei"

    with pytest.raises(CorpusError) as info:
        load_corpus(_write_good_with(tmp_path, mutate))
    assert info.value.problems == ["entry 1 (珍珠奶茶), field region: unknown field"]


def test_corpus_that_is_not_an_array_fails() -> None:
    with pytest.raises(CorpusError) as info:
        load_corpus(FIXTURES / "bad_not_an_array.json")
    # Only the top-level type, not the file's content.
    assert info.value.problems == ["corpus: the file holds an object, not an array of entries"]


def test_invalid_json_fails() -> None:
    with pytest.raises(CorpusError) as info:
        load_corpus(FIXTURES / "bad_json_syntax.json")
    assert info.value.problems[0].startswith("not valid JSON:")


def test_entry_point_prints_count_for_good_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(GOOD)]) == 0
    assert capsys.readouterr().out == "3\n"


def test_entry_point_exits_non_zero_on_bad_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(FIXTURES / "bad_wrong_type.json")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "entry 0 (蚵仔煎), field aliases:" in captured.err


def test_entry_point_exits_non_zero_on_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "absent.json")]) == 1
    assert capsys.readouterr().out == ""
