"""Tests for the name-check helpers: normalization, Chinese contains and equals, the English rule
[R22], and the Chinese-character detector [R5]."""

from dont_say_oyster.matching import (
    chinese_contains,
    chinese_equals,
    english_contains,
    has_chinese_characters,
    normalize,
)


def test_full_width_letters_and_digits_equal_half_width() -> None:
    assert chinese_equals("ＱＱ蛋１２３", ["QQ蛋123"]) == ["QQ蛋123"]


def test_traditional_and_simplified_match_both_ways() -> None:
    assert chinese_equals("麵線", ["面线"]) == ["面线"]
    assert chinese_equals("面线", ["麵線"]) == ["麵線"]
    assert chinese_equals("烤牡蠣", ["烤牡蛎"]) == ["烤牡蛎"]
    assert chinese_equals("烤牡蛎", ["烤牡蠣"]) == ["烤牡蠣"]


def test_dou_gan_variants_normalize_to_the_same_string() -> None:
    assert normalize("豆干") == normalize("豆乾")


def test_spaces_and_punctuation_are_ignored() -> None:
    assert chinese_equals("蚵仔 煎！", ["蚵仔煎"]) == ["蚵仔煎"]


def test_contains_is_substring_and_equals_is_not() -> None:
    assert chinese_contains("烤蚵仔好吃", ["烤蚵仔"]) == ["烤蚵仔"]
    assert chinese_equals("烤蚵仔好吃", ["烤蚵仔"]) == []


def test_matched_items_are_returned_in_list_order_as_given() -> None:
    items = ["蚵仔煎", "麵線", "臭豆腐"]
    assert chinese_contains("面线和蚵仔 煎", items) == ["蚵仔煎", "麵線"]
    assert english_contains("oyster and peaches", ["Peach", "squid", "Oyster"]) == [
        "Peach",
        "Oyster",
    ]


def test_english_matches_with_case_changed_and_as_a_phrase() -> None:
    assert english_contains("Is it a Grilled Oyster?", ["grilled oyster"]) == ["grilled oyster"]


def test_english_matches_plural_with_s_or_es() -> None:
    assert english_contains("Does it have oysters?", ["oyster"]) == ["oyster"]
    assert english_contains("Are there peaches?", ["peach"]) == ["peach"]


def test_english_item_inside_a_longer_word_does_not_match() -> None:
    assert english_contains("drawn on the street", ["raw"]) == []
    assert english_contains("Is it eggplant?", ["egg"]) == []


def test_chinese_character_next_to_an_english_item_is_a_word_boundary() -> None:
    assert english_contains("很好吃oyster", ["oyster"]) == ["oyster"]
    assert english_contains("oyster蚵", ["oyster"]) == ["oyster"]
    assert english_contains("drawn", ["raw"]) == []


def test_hyphenated_item_matches_spaced_and_upper_case_text() -> None:
    assert english_contains("is it tang a bi ko", ["tang-a-bi-ko"]) == ["tang-a-bi-ko"]
    assert english_contains("TANG-A-BI-KO", ["tang-a-bi-ko"]) == ["tang-a-bi-ko"]


def test_apostrophes_straight_and_curly_are_removed() -> None:
    item = "Pig's blood cake"
    assert english_contains("pigs blood cake", [item]) == [item]
    assert english_contains("pig’s blood cake", [item]) == [item]
    assert english_contains("Pig's Blood Cake", [item]) == [item]


def test_hyphen_in_text_is_a_word_boundary() -> None:
    assert english_contains("an oyster-omelet stall", ["oyster"]) == ["oyster"]


def test_spaced_item_matches_hyphenated_text() -> None:
    assert english_contains("oyster-omelet", ["Oyster Omelet"]) == ["Oyster Omelet"]


def test_full_width_english_text_matches() -> None:
    assert english_contains("ＯＹＳＴＥＲ", ["oyster"]) == ["oyster"]


def test_runs_of_spaces_collapse_to_one() -> None:
    assert english_contains("grilled   oyster", ["grilled oyster"]) == ["grilled oyster"]


def test_detector_finds_han_and_not_other_scripts_or_punctuation() -> None:
    assert has_chinese_characters("雪Q餅")
    assert has_chinese_characters("蚵")
    for text in ["QQ", "すし", "김밥", "ㄅ", "，"]:
        assert not has_chinese_characters(text), text
