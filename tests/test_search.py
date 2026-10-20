"""Tests for the search tool [R44]-[R46], on the fixture corpus in tests/fixtures/search."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from ollama import Tool

from dont_say_oyster.corpus import SCHEMA_PATH, CorpusEntry, load_corpus
from dont_say_oyster.search import (
    FIELDS,
    PROMPT_PATH,
    SearchQuery,
    SearchResult,
    search,
    search_tool,
)

CORPUS = load_corpus(Path(__file__).parent / "fixtures" / "search" / "corpus.json")


def query(**args: Any) -> Any:
    return SearchQuery.model_validate(args)


def names(result: SearchResult) -> list[str]:
    return [hit.official_name for hit in result.hits]


def call(args: dict[str, Any], corpus: list[CorpusEntry] = CORPUS) -> ToolMessage:
    message = search_tool(corpus).invoke(
        {"type": "tool_call", "id": "call-1", "name": "search", "args": args}
    )
    assert isinstance(message, ToolMessage)
    return message


def schema_values() -> dict[str, list[str]]:
    entry = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["items"]
    attributes = entry["properties"]["attributes"]["properties"]
    return {field: attributes[field]["items"]["enum"] for field in attributes}


# Filters and keywords [R44].


def test_filter_only() -> None:
    assert names(search(CORPUS, query(dish_type=["Drink"]))) == ["珍珠奶茶", "豆漿"]


def test_two_values_in_one_field_either_passes() -> None:
    result = search(CORPUS, query(occasion=["Breakfast", "Souvenir"]))
    assert names(result) == ["新竹米粉", "平價餅", "鳳梨酥", "蛋餅", "豆漿"]


def test_two_fields_both_must_pass() -> None:
    assert names(search(CORPUS, query(cooking_method=["Deep-Fried"]))) == ["臭豆腐", "鹽酥雞"]
    assert names(search(CORPUS, query(flavor=["Spicy"]))) == ["鹽酥雞"]
    result = search(CORPUS, query(cooking_method=["Deep-Fried"], flavor=["Fermented"]))
    assert names(result) == ["臭豆腐"]


def test_entry_with_no_occasion_does_not_pass_an_occasion_filter() -> None:
    result = search(CORPUS, query(occasion=["Night Market"]))
    assert names(result) == ["蚵仔煎", "臭豆腐", "大腸包小腸", "鹽酥雞"]
    assert any(not entry.attributes.occasion for entry in CORPUS)


def test_filter_plus_keyword_returns_only_entries_passing_both() -> None:
    assert names(search(CORPUS, query(main_ingredients=["Pork"], keywords=["rice"]))) == [
        "滷肉飯",
        "粽子",
    ]


def test_two_keywords_return_entries_matching_either() -> None:
    result = search(CORPUS, query(keywords=["tofu", "cake"]))
    assert names(result) == ["平價餅", "鳳梨酥", "臭豆腐"]


def test_keyword_matches_a_whole_word_or_its_plural_not_a_substring() -> None:
    assert "炒米粉" in names(search(CORPUS, query(keywords=["noodle"])))  # "Rice Noodles"
    assert "新竹米粉" in names(search(CORPUS, query(keywords=["noodle"])))  # "Rice Noodle"
    assert "新竹米粉" not in names(search(CORPUS, query(keywords=["noodles"])))
    assert "炒米粉" in names(search(CORPUS, query(keywords=["noodles"])))
    assert "平價餅" not in names(search(CORPUS, query(keywords=["rice"])))  # "Fair Price Cake"


def test_keyword_is_matched_after_the_english_normalization() -> None:
    assert names(search(CORPUS, query(keywords=["Stinky-Tofu"]))) == ["臭豆腐"]
    assert names(search(CORPUS, query(keywords=["pork belly"]))) == ["刈包"]


def test_keyword_with_no_latin_letters_is_searched_and_matches_nothing() -> None:
    message = call({"keywords": ["蚵仔"]})
    assert message.status == "success"
    assert message.artifact == SearchResult(hits=(), more=False)


# The limit [R46] and the result shape [R45].


def test_more_than_ten_matches_return_the_first_ten_and_say_there_are_more() -> None:
    result = search(CORPUS, query(flavor=["Savory"]))
    assert names(result) == [
        "蚵仔煎",
        "炒米粉",
        "新竹米粉",
        "滷肉飯",
        "臭豆腐",
        "蛋餅",
        "牛肉麵",
        "大腸包小腸",
        "鹽酥雞",
        "肉圓",
    ]
    assert result.more is True
    content = json.loads(call({"flavor": ["Savory"]}).text)
    assert len(content["results"]) == 10
    assert content["more_results"] is True


def test_exactly_ten_matches_do_not_say_there_are_more() -> None:
    result = search(CORPUS[:14], query(flavor=["Savory"]))
    assert len(result.hits) == 10
    assert result.more is False
    assert json.loads(call({"flavor": ["Savory"]}, CORPUS[:14]).text)["more_results"] is False


def test_each_result_holds_exactly_names_and_attributes() -> None:
    message = call({"keywords": ["oyster omelette"]})
    assert json.loads(message.text) == {
        "results": [
            {
                "official_name": "蚵仔煎",
                "aliases": ["蚵煎"],
                "english_names": ["oyster omelette", "o-a-jian"],
                "attributes": {
                    "dish_type": ["Snack"],
                    "main_ingredients": ["Seafood", "Egg", "Starch"],
                    "cooking_method": ["Pan-Fried"],
                    "flavor": ["Savory", "Sweet"],
                    "physical_form": ["Sauced"],
                    "occasion": ["Night Market"],
                },
            }
        ],
        "more_results": False,
    }
    assert "omelette" in CORPUS[0].forbidden_words
    assert not hasattr(message.artifact.hits[0], "forbidden_words")


def test_content_is_unescaped_json_and_artifact_is_the_same_result() -> None:
    message = call({"dish_type": ["Drink"]})
    assert message.status == "success"
    assert "珍珠奶茶" in message.text
    assert message.artifact == search(CORPUS, query(dish_type=["Drink"]))
    assert json.loads(message.text) == message.artifact.as_json()


# Calls the schema rejects (Recovery, forks, and replay, Model errors).


class Untouchable(list[CorpusEntry]):
    """A corpus that fails the test when searched."""

    def __iter__(self) -> Iterator[CorpusEntry]:
        raise AssertionError("the corpus was searched")


def assert_rejected(args: dict[str, Any], *expected: str) -> str:
    message = call(args, Untouchable(CORPUS))
    assert message.status == "error"
    assert message.artifact is None
    for text in expected:
        assert text in message.text
    assert "errors.pydantic.dev" not in message.text
    return message.text


def test_no_filter_and_no_keyword_is_rejected() -> None:
    rejected = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))["messages"]
    text = assert_rejected({}, rejected["rejected"], rejected["no_filter_or_keyword"])
    assert assert_rejected({"dish_type": [], "keywords": []}) == text


def test_value_not_in_its_list_is_rejected_without_a_search() -> None:
    assert_rejected({"main_ingredients": ["Milk", "Boba"]}, "main_ingredients[1]", "'Boba'")


def test_value_with_wrong_case_is_rejected() -> None:
    assert_rejected({"cooking_method": ["no cooking"]}, "cooking_method[0]", "'no cooking'")


def test_unknown_argument_is_rejected() -> None:
    assert_rejected({"flavor": ["Sweet"], "colour": ["Red"]}, "colour")


def test_filter_given_as_a_string_is_rejected() -> None:
    assert_rejected({"flavor": "Sweet"}, "flavor")


def test_keyword_empty_after_normalization_is_rejected() -> None:
    assert_rejected({"keywords": ["tofu", "!!"]}, "keywords[1]", "'!!'")
    assert_rejected({"keywords": ["   "]}, "keywords[0]")
    assert_rejected({"keywords": [""]}, "keywords[0]")


def test_duplicate_values_are_searched_once() -> None:
    message = call({"main_ingredients": ["Milk", "Milk"], "keywords": ["tea", "tea"]})
    assert message.status == "success"
    assert message.artifact == search(CORPUS, query(main_ingredients=["Milk"], keywords=["tea"]))
    assert query(main_ingredients=["Soy", "Milk", "Soy"]).main_ingredients == ["Soy", "Milk"]


# The schema the model gets [R44].


def openai_parameters() -> dict[str, Any]:
    parameters: dict[str, Any] = convert_to_openai_tool(search_tool(CORPUS))["function"][
        "parameters"
    ]
    return parameters


def test_fields_are_the_six_attribute_fields() -> None:
    assert list(FIELDS) == list(schema_values())
    assert list(openai_parameters()["properties"]) == [*FIELDS, "keywords"]


def test_tool_schema_lists_each_fields_values_exactly_as_schema_json() -> None:
    properties = openai_parameters()["properties"]
    for field, values in schema_values().items():
        assert properties[field]["type"] == "array"
        assert properties[field]["items"]["enum"] == values


def test_enums_survive_the_ollama_tool_type() -> None:
    # The ollama client drops keys it does not name; an anyOf would lose the enum (T3).
    sent = Tool.model_validate(convert_to_openai_tool(search_tool(CORPUS))).model_dump(
        exclude_none=True
    )
    properties = sent["function"]["parameters"]["properties"]
    for field, values in schema_values().items():
        assert properties[field]["items"]["enum"] == values
    assert properties["keywords"]["items"]["type"] == "string"
    assert sent["function"]["parameters"].get("required", []) == []


def test_descriptions_come_from_the_prompt_file() -> None:
    texts = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    assert set(texts["fields"]) == set(FIELDS)
    tool = convert_to_openai_tool(search_tool(CORPUS))["function"]
    assert tool["name"] == "search"
    assert tool["description"] == texts["tool"]
    for field in FIELDS:
        assert tool["parameters"]["properties"][field]["description"] == texts["fields"][field]
    assert tool["parameters"]["properties"]["keywords"]["description"] == texts["keywords"]


def test_field_descriptions_carry_no_entry_cardinality() -> None:
    # "(required, one)" describes corpus entries; in a filter it could read as the filter's rule.
    fields = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))["fields"]
    for text in fields.values():
        assert "(required" not in text
        assert "(optional" not in text


@pytest.mark.parametrize("field", FIELDS)
def test_every_listed_value_can_be_searched(field: str) -> None:
    for value in schema_values()[field]:
        assert call({field: [value]}).status == "success"
