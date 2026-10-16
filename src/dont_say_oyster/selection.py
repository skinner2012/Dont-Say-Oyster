"""Card selection: chooses the forty official names the cards are built from, and the order the
batch manifests list them in. Run as `uv run select-cards CORPUS SELECTION` to write the
selection, a JSON array of forty official names in the order of the ordering criterion; it is
the input of `pick-distractors --names` and of `build-cards`.

Both criteria are the author's, in T7 of `docs/tasks/M1-corpus.md`:

- Selection: the corpus is split by Dish type and Physical form into the ten GROUPS below, in
  that order. Each group gets a quota in proportion to its size, forty in all, by the
  largest-remainder method (integer parts first, then one card each to the groups with the
  largest remainders, ties to the group listed first). One `random.Random(SEED)` is shared by
  all groups, which are drawn one after another in order: each draw removes the entry at
  `rng.randrange(len(pool))` from the group's pool (the pool starts in corpus file order) and
  rejects it when its five attribute fields other than Occasion equal those of a card already
  drawn from any group. Fields are compared as sets of values, since the order of a field's
  values carries no meaning.
- Order: round-robin over the groups in order, the first card drawn from each group, then the
  second from each, and so on, skipping a group with no cards left; within a group, the order
  it was drawn in.

Changing the seed means changing T7's selection criterion and SEED together."""

import argparse
import json
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dont_say_oyster.corpus import CorpusEntry, CorpusError, load_corpus

SEED = 2026
CARD_COUNT = 40


@dataclass(frozen=True)
class Group:
    label: str
    dish_type: str
    physical_forms: frozenset[str]


GROUPS = (
    Group("Meal dry or sauced", "Meal", frozenset({"Dry", "Sauced"})),
    Group("Meal soup or thick soup", "Meal", frozenset({"Soup", "Thick Soup"})),
    Group("Snack dry", "Snack", frozenset({"Dry"})),
    Group("Snack sauced", "Snack", frozenset({"Sauced"})),
    Group("Snack soup or thick soup", "Snack", frozenset({"Soup", "Thick Soup"})),
    Group("Dessert dry", "Dessert", frozenset({"Dry"})),
    Group("Dessert soup or thick soup", "Dessert", frozenset({"Soup", "Thick Soup"})),
    Group("Dessert shaved ice or ice pop", "Dessert", frozenset({"Shaved Ice", "Ice Pop"})),
    Group("Drink smooth", "Drink", frozenset({"Smooth Drink"})),
    Group("Drink with add-ins or slush", "Drink", frozenset({"Drink with Add-ins", "Slush"})),
)

AttributeKey = tuple[frozenset[str], ...]


class SelectionError(Exception):
    """The criteria cannot be applied to this corpus or this selection."""


def group_index(entry: CorpusEntry) -> int:
    """The index in GROUPS of the entry's group. The corpus schema allows exactly one Dish type
    and one Physical form; an entry that fits no group is an error."""
    attributes = entry.attributes
    for index, group in enumerate(GROUPS):
        if (
            attributes.dish_type == (group.dish_type,)
            and len(attributes.physical_form) == 1
            and attributes.physical_form[0] in group.physical_forms
        ):
            return index
    raise SelectionError(
        f"{entry.official_name}: Dish type {list(attributes.dish_type)} and Physical form "
        f"{list(attributes.physical_form)} fit none of the ten groups"
    )


def attribute_key(entry: CorpusEntry) -> AttributeKey:
    """The five attribute fields other than Occasion, each as a set of values."""
    a = entry.attributes
    fields = (a.dish_type, a.main_ingredients, a.cooking_method, a.flavor, a.physical_form)
    return tuple(frozenset(values) for values in fields)


def quotas(sizes: Sequence[int], total: int = CARD_COUNT) -> list[int]:
    """Each group's quota, in proportion to its size, `total` in all, by the largest-remainder
    method; ties go to the group listed first. Exact integer arithmetic: the share of a group of
    size n is total * n / sum(sizes), its integer part total * n // sum(sizes)."""
    whole = sum(sizes)
    if whole == 0:
        raise SelectionError("the corpus has no entries")
    result = [total * n // whole for n in sizes]
    remainders = [total * n % whole for n in sizes]
    # sorted is stable, so among equal remainders the group listed first comes first.
    by_remainder = sorted(range(len(sizes)), key=lambda i: -remainders[i])
    for i in by_remainder[: total - sum(result)]:
        result[i] += 1
    return result


def draw(corpus: Sequence[CorpusEntry], seed: int = SEED) -> list[list[CorpusEntry]]:
    """Each group's cards, in the order drawn. Raises SelectionError when a group's pool runs
    out before its quota is filled."""
    pools: list[list[CorpusEntry]] = [[] for _ in GROUPS]
    for entry in corpus:
        pools[group_index(entry)].append(entry)
    rng = random.Random(seed)
    drawn_keys: set[AttributeKey] = set()
    drawn: list[list[CorpusEntry]] = []
    for group, pool, quota in zip(GROUPS, pools, quotas([len(p) for p in pools]), strict=True):
        cards: list[CorpusEntry] = []
        while len(cards) < quota:
            if not pool:
                raise SelectionError(
                    f"group {group.label!r}: only {len(cards)} entries differ in their five "
                    f"attribute fields from the cards already drawn; its quota is {quota}"
                )
            entry = pool.pop(rng.randrange(len(pool)))
            key = attribute_key(entry)
            if key in drawn_keys:
                continue
            drawn_keys.add(key)
            cards.append(entry)
        drawn.append(cards)
    return drawn


def round_robin[T](groups: Sequence[Sequence[T]]) -> list[T]:
    """The first item of each group in order, then the second of each, and so on, skipping a
    group with no items left."""
    return [g[i] for i in range(max((len(g) for g in groups), default=0)) for g in groups
            if i < len(g)]


def select(corpus: Sequence[CorpusEntry], seed: int = SEED) -> list[str]:
    """The forty official names, in the order of the ordering criterion."""
    return [entry.official_name for entry in round_robin(draw(corpus, seed))]


def order(names: Sequence[str], corpus: Sequence[CorpusEntry]) -> list[str]:
    """Apply the ordering criterion to a selection: round-robin over the groups, each group's
    names in the order the selection lists them (for select's output, the order drawn).
    Returns the selection unchanged when it is already in that order."""
    by_name = {e.official_name: e for e in corpus}
    groups: list[list[str]] = [[] for _ in GROUPS]
    for name in names:
        if name not in by_name:
            raise SelectionError(f"not an official name in the corpus: {name}")
        groups[group_index(by_name[name])].append(name)
    return round_robin(groups)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="select-cards",
        description=f"Select the forty official names (seed {SEED}) and write them, in card "
        "order, as a JSON array.",
    )
    parser.add_argument("corpus", type=Path, help="path to the corpus JSON file")
    parser.add_argument("selection", type=Path, help="path to write the selection to")
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.corpus)
        drawn = draw(corpus)
        names = [entry.official_name for entry in round_robin(drawn)]
        args.selection.write_text(
            json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (CorpusError, SelectionError, OSError) as e:
        print(e, file=sys.stderr)
        return 1
    for group, cards in zip(GROUPS, drawn, strict=True):
        print(f"{group.label}: {len(cards)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
