"""Card builder, card loader, and manifest check. Run as
`uv run build-cards CORPUS SELECTION DISTRACTORS CARDS BATCHES` to write the cards file and one
manifest per variant, `BATCHES/V0/manifest.json` to `BATCHES/V3/manifest.json`.

The cards file is a JSON array of cards, one per selected official name, in card order. Each
card holds `card_id` (see `card_id`), `distractors` (the name's current list in the distractor
file), and every other field copied from its corpus entry: `official_name`, `aliases`,
`english_names`, `forbidden_words`, `attributes` (SPEC.md, Corpus and Cards; [R9]). The file is
never edited by hand; it is rebuilt.

A manifest is a JSON object holding `variant`, `cards` (the cards file path, relative to the repo
root when the file is inside it), and `card_ids`, the forty card ids in card order. The order is
the ordering criterion applied to the selection (`selection.order`)."""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from dont_say_oyster.corpus import SCHEMA_PATH, Attributes, CorpusEntry, CorpusError, load_corpus
from dont_say_oyster.distractors import DistractorFileError, DistractorRecord, load_distractors
from dont_say_oyster.selection import CARD_COUNT, SelectionError, order

REPO_ROOT = Path(__file__).resolve().parents[2]
SELECTION_PATH = REPO_ROOT / "data" / "cards" / "selection.json"
DISTRACTORS_PATH = REPO_ROOT / "data" / "cards" / "distractors.json"
CARDS_PATH = REPO_ROOT / "data" / "cards" / "cards.json"
BATCHES_DIR = REPO_ROOT / "batches"
VARIANTS = ("V0", "V1", "V2", "V3")
MANIFEST_NAME = "manifest.json"
MAX_DISTRACTORS = 5


@dataclass(frozen=True)
class Card:
    card_id: str
    official_name: str
    aliases: tuple[str, ...]
    english_names: tuple[str, ...]
    forbidden_words: tuple[str, ...]
    attributes: Attributes
    distractors: tuple[str, ...]


class CardFileError(Exception):
    """The cards file cannot be loaded. `problems` holds one line per error."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"{path}:\n" + "\n".join(f"  {p}" for p in problems))
        self.problems = problems


class BuildError(Exception):
    """The build command cannot build the cards from its inputs."""


class ManifestError(Exception):
    """The manifests do not match each other or the cards file. `problems` holds one line per
    error."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def card_id(official_name: str) -> str:
    """The card id: `card-` followed by the first 8 hex digits of the SHA-256 of the official
    name's UTF-8 bytes. It depends on the name only, so it is the same on every run over the same
    corpus and does not depend on the card's position in the order."""
    return "card-" + hashlib.sha256(official_name.encode("utf-8")).hexdigest()[:8]


def manifest_paths(batches: Path = BATCHES_DIR) -> list[Path]:
    """The four manifests' paths, V0 to V3, under the batches directory."""
    return [batches / variant / MANIFEST_NAME for variant in VARIANTS]


def _card_schema() -> dict[str, Any]:
    """A card's shape: the corpus entry's (from the corpus schema, so attributes are checked the
    same way) plus `card_id` and `distractors`. The count and uniqueness of distractors are
    checked in `_card_problems`, so their errors say what they are."""
    entry: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["items"]
    return {
        **entry,
        "required": [*entry["required"], "card_id", "distractors"],
        "properties": {
            **entry["properties"],
            "card_id": {"type": "string", "minLength": 1},
            "distractors": {"type": "array", "items": {"type": "string"}},
        },
    }


def _label(data: list[Any], index: int) -> str:
    name = data[index].get("official_name") if isinstance(data[index], dict) else None
    if isinstance(name, str) and name:
        return f"card {index} ({name})"
    return f"card {index}"


def _card_problems(data: Any, corpus: Sequence[CorpusEntry]) -> list[str]:
    """Every error in the cards data: not an array; a card count other than forty; a card that
    does not have the card shape (a missing, unknown, or ill-typed field); a duplicate card id;
    more than five distractors; a duplicate distractor on one card; a distractor that is not the
    official name of another corpus entry [R17]. Cards are numbered from 0."""
    if not isinstance(data, list):
        return ["the file must be a JSON array of cards"]
    problems = []
    if len(data) != CARD_COUNT:
        problems.append(f"holds {len(data)} cards, not {CARD_COUNT}")

    validator = Draft202012Validator(_card_schema())
    for index, card in enumerate(data):
        for error in validator.iter_errors(card):
            field = ".".join(str(p) for p in error.absolute_path)
            if error.validator == "required":
                missing = [k for k in error.validator_value if k not in error.instance]
                prefix = f"{field}." if field else ""
                problems += [f"{_label(data, index)}, field {prefix}{k}: missing field"
                             for k in missing]
            else:
                where = f"{_label(data, index)}, field {field}" if field else _label(data, index)
                problems.append(f"{where}: {error.message}")
    if problems:
        return problems

    ids = Counter(card["card_id"] for card in data)
    official = {e.official_name for e in corpus}
    for index, card in enumerate(data):
        label = _label(data, index)
        if ids[card["card_id"]] > 1:
            problems.append(f"{label}: card id {card['card_id']} is on more than one card")
        distractors = card["distractors"]
        if len(distractors) > MAX_DISTRACTORS:
            problems.append(
                f"{label}: {len(distractors)} distractors, more than {MAX_DISTRACTORS}"
            )
        for name, count in Counter(distractors).items():
            if count > 1:
                problems.append(f"{label}: distractor {name} is listed {count} times")
            if name == card["official_name"]:
                problems.append(f"{label}: distractor {name} is the card itself")
            elif name not in official:
                problems.append(
                    f"{label}: distractor {name} is not the official name of a corpus entry"
                )
    return problems


def load_cards(path: Path, corpus: Sequence[CorpusEntry]) -> list[Card]:
    """Load the cards file at `path`, in file order, checking its distractors against
    `corpus`. Raises CardFileError listing every error `_card_problems` finds."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CardFileError(path, [f"not valid JSON: {e}"]) from e
    problems = _card_problems(data, corpus)
    if problems:
        raise CardFileError(path, problems)
    return [
        Card(
            card_id=card["card_id"],
            official_name=card["official_name"],
            aliases=tuple(card["aliases"]),
            english_names=tuple(card["english_names"]),
            forbidden_words=tuple(card["forbidden_words"]),
            attributes=Attributes(**{k: tuple(v) for k, v in card["attributes"].items()}),
            distractors=tuple(card["distractors"]),
        )
        for card in data
    ]


_MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["variant", "cards", "card_ids"],
    "additionalProperties": False,
    "properties": {
        "variant": {"type": "string"},
        "cards": {"type": "string"},
        "card_ids": {"type": "array", "items": {"type": "string"}},
    },
}


def check_manifests(manifests: Sequence[Path], cards: Path) -> None:
    """Fail (raise ManifestError) when the manifests do not all list the same card ids in the
    same order, or when one does not list exactly the cards file's ids (each id once, none
    missing, none extra). The cards file is read only for its ids; `load_cards` checks the
    rest."""
    try:
        card_data = json.loads(cards.read_text(encoding="utf-8"))
        card_ids = Counter(card["card_id"] for card in card_data)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        raise ManifestError([f"{cards}: cannot read the card ids: {e!r}"]) from e
    if not manifests:
        raise ManifestError(["no manifests given"])

    orders: list[list[str]] = []
    problems = []
    validator = Draft202012Validator(_MANIFEST_SCHEMA)
    for path in manifests:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ManifestError([f"{path}: not valid JSON: {e}"]) from e
        errors = [e.message for e in validator.iter_errors(data)]
        if errors:
            raise ManifestError([f"{path}: {m}" for m in errors])
        orders.append(data["card_ids"])

    for path, ids in zip(manifests, orders, strict=True):
        if ids != orders[0]:
            problems.append(f"{path}: card order differs from {manifests[0]}")
        listed = Counter(ids)
        missing = sorted((card_ids - listed).elements())
        extra = sorted((listed - card_ids).elements())
        if missing:
            problems.append(f"{path}: does not list cards {', '.join(missing)}")
        if extra:
            problems.append(
                f"{path}: lists ids not in {cards}, or more times than it holds them: "
                f"{', '.join(extra)}"
            )
    if problems:
        raise ManifestError(problems)


def build_cards(
    corpus: Sequence[CorpusEntry],
    selection: Sequence[str],
    distractors: dict[str, DistractorRecord],
) -> list[dict[str, Any]]:
    """The cards data for `selection`, in card order, checked by the card loader's checks."""
    repeated = sorted({n for n in selection if selection.count(n) > 1})
    if repeated:
        raise BuildError(f"named more than once in the selection: {', '.join(repeated)}")
    try:
        names = order(selection, corpus)
    except SelectionError as e:
        raise BuildError(str(e)) from e
    missing = [n for n in names if n not in distractors]
    if missing:
        raise BuildError(f"not in the distractor file: {', '.join(missing)}")

    by_name = {e.official_name: e for e in corpus}
    cards = []
    for name in names:
        entry = by_name[name]
        a = entry.attributes
        cards.append(
            {
                "card_id": card_id(name),
                "official_name": name,
                "aliases": list(entry.aliases),
                "english_names": list(entry.english_names),
                "forbidden_words": list(entry.forbidden_words),
                "attributes": {
                    "dish_type": list(a.dish_type),
                    "main_ingredients": list(a.main_ingredients),
                    "cooking_method": list(a.cooking_method),
                    "flavor": list(a.flavor),
                    "physical_form": list(a.physical_form),
                    "occasion": list(a.occasion),
                },
                "distractors": list(distractors[name].current),
            }
        )
    problems = _card_problems(cards, corpus)
    if problems:
        raise BuildError("the cards would not load:\n" + "\n".join(f"  {p}" for p in problems))
    return cards


def _path_ref(path: Path) -> str:
    """How a manifest names the cards file: relative to the repo root when inside it, so the
    manifest is the same whichever way the path was given; otherwise absolute."""
    resolved = path.resolve()
    if resolved.is_relative_to(REPO_ROOT):
        return resolved.relative_to(REPO_ROOT).as_posix()
    return resolved.as_posix()


def _write_json(path: Path, data: Any) -> None:
    """Write `data` as JSON, replacing the file in one step so a crash never leaves half a
    file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def manifest_data(cards_data: list[dict[str, Any]], cards: Path) -> list[dict[str, Any]]:
    """The four manifests, V0 to V3, for the cards data written to `cards`."""
    ids = [card["card_id"] for card in cards_data]
    return [{"variant": v, "cards": _path_ref(cards), "card_ids": ids} for v in VARIANTS]


def write_build(cards_data: list[dict[str, Any]], cards: Path, batches: Path) -> None:
    """Write the cards file and the four manifests."""
    _write_json(cards, cards_data)
    for data, path in zip(manifest_data(cards_data, cards), manifest_paths(batches), strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, data)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-cards",
        description="Build the cards file and the four batch manifests from the corpus, the "
        "selection, and the distractor file.",
    )
    parser.add_argument("corpus", type=Path, help="path to the corpus JSON file")
    parser.add_argument("selection", type=Path, help="the selection: JSON array of names")
    parser.add_argument("distractors", type=Path, help="path to the distractor file")
    parser.add_argument("cards", type=Path, help="path to write the cards file to")
    parser.add_argument(
        "batches", type=Path, help="the batches directory; manifests go in its V0 to V3"
    )
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.corpus)
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        if not isinstance(selection, list) or not all(isinstance(n, str) for n in selection):
            raise BuildError(f"{args.selection}: not a JSON array of official names")
        cards_data = build_cards(corpus, selection, load_distractors(args.distractors))
        write_build(cards_data, args.cards, args.batches)
    except (
        CorpusError,
        DistractorFileError,
        BuildError,
        OSError,
        json.JSONDecodeError,
    ) as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
