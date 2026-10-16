"""The generated fixture corpus and fixture distractor file that the selection, build, and data
tests run on.

The corpus has an entry in every one of the ten groups, groups of unequal size (so the quotas
have remainders and the round-robin skips groups that run out), and in the group "Snack dry"
three entries whose five attribute fields other than Occasion are the same, so the draw has
cards to reject. Every other entry differs from every other in those five fields."""

import json
from pathlib import Path
from typing import Any

from dont_say_oyster.distractors import DistractorRecord, Pick, PickRound, write_distractors

# Per group, in the order of selection.GROUPS: Dish type, the Physical forms its entries cycle
# through, and how many entries it has.
GROUP_SHAPES: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("Meal", ("Dry", "Sauced"), 7),
    ("Meal", ("Soup", "Thick Soup"), 4),
    ("Snack", ("Dry",), 14),
    ("Snack", ("Sauced",), 3),
    ("Snack", ("Soup", "Thick Soup"), 5),
    ("Dessert", ("Dry",), 9),
    ("Dessert", ("Soup", "Thick Soup"), 4),
    ("Dessert", ("Shaved Ice", "Ice Pop"), 3),
    ("Drink", ("Smooth Drink",), 3),
    ("Drink", ("Drink with Add-ins", "Slush"), 2),
)
SIZE = sum(n for _, _, n in GROUP_SHAPES)  # 54
# Entries 0, 1, and 2 of "Snack dry" share their five attribute fields.
SAME_ATTRIBUTES = (0, 1, 2)
SNACK_DRY = 2

INGREDIENTS = (
    "Rice", "Wheat", "Noodles", "Starch", "Root Vegetables", "Soy", "Beans and Seeds", "Pork",
    "Beef", "Poultry", "Seafood", "Other Meat", "Egg", "Vegetables", "Fruit",
    "Sugar and Sweeteners", "Herbs", "Tea", "Milk",
)
OCCASIONS: tuple[list[str], ...] = ([], ["Breakfast"], ["Night Market"], ["Festival"], ["Souvenir"])


def official_name(number: int) -> str:
    return f"測試小吃{number:02d}"


def corpus_data() -> list[dict[str, Any]]:
    """The fixture corpus, groups one after another in GROUPS order. Within a group, entry i
    has ingredient i (so no two entries in a group share their five fields) except the
    SAME_ATTRIBUTES entries of "Snack dry", which all take ingredient 0."""
    entries: list[dict[str, Any]] = []
    for group, (dish_type, forms, count) in enumerate(GROUP_SHAPES):
        for i in range(count):
            number = len(entries)
            same = group == SNACK_DRY and i in SAME_ATTRIBUTES
            ingredient = INGREDIENTS[0 if same else i]
            flavor = ["Sweet"] if dish_type in ("Dessert", "Drink") else ["Savory"]
            entries.append(
                {
                    "official_name": official_name(number),
                    "aliases": [f"測試別名{number:02d}"],
                    "english_names": [f"test snack {number}"],
                    "forbidden_words": [f"word{number}"],
                    "attributes": {
                        "dish_type": [dish_type],
                        "main_ingredients": [ingredient],
                        "cooking_method": ["Boiled"],
                        "flavor": flavor,
                        "physical_form": [forms[0] if same else forms[i % len(forms)]],
                        "occasion": OCCASIONS[number % len(OCCASIONS)],
                    },
                }
            )
    return entries


def write_corpus(path: Path) -> Path:
    path.write_text(json.dumps(corpus_data(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def current_list(number: int) -> tuple[str, ...]:
    """Entry `number`'s current distractor list: the official names of the next `number % 6`
    entries, so the lists run from empty to five names. Every third entry's list is a hand
    edit: its round kept those names in the other order and one more."""
    return tuple(official_name((number + k) % SIZE) for k in range(1, number % 6 + 1))


def distractor_records() -> dict[str, DistractorRecord]:
    records = {}
    for number in range(SIZE):
        current = current_list(number)
        kept = current
        if number % 3 == 0:
            kept = (*reversed(current), official_name((number + 7) % SIZE))[:5]
        round_1 = PickRound(1, tuple(Pick(n, "why") for n in kept), (), None)
        records[official_name(number)] = DistractorRecord(rounds=(round_1,), current=current)
    return records


def write_distractor_file(path: Path) -> Path:
    write_distractors(path, distractor_records())
    return path
