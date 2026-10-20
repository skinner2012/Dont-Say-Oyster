"""Corpus loader: validates the corpus file against `data/corpus/schema.json` and reads it into
typed entries. Run as `uv run load-corpus PATH` to load a corpus file and print its entry count."""

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from dont_say_oyster.matching import normalize

# The package is installed editable from the repo, so the schema is found next to it.
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "corpus" / "schema.json"


@dataclass(frozen=True)
class Attributes:
    dish_type: tuple[str, ...]
    main_ingredients: tuple[str, ...]
    cooking_method: tuple[str, ...]
    flavor: tuple[str, ...]
    physical_form: tuple[str, ...]
    occasion: tuple[str, ...]


@dataclass(frozen=True)
class CorpusEntry:
    official_name: str
    aliases: tuple[str, ...]
    english_names: tuple[str, ...]
    forbidden_words: tuple[str, ...]
    attributes: Attributes


class CorpusError(Exception):
    """The corpus file cannot be loaded. `problems` holds one line per error. An error in an
    entry names the entry (its index from 0, and its official name when present) and the field;
    an error about the whole file (not valid JSON, not an array) names neither."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        numbering = (
            " (entries are numbered from 0)"
            if any(p.startswith("entry ") for p in problems)
            else ""
        )
        super().__init__(f"{path}{numbering}:\n" + "\n".join(f"  {p}" for p in problems))
        self.problems = problems


def load_corpus(path: Path, schema_path: Path = SCHEMA_PATH) -> list[CorpusEntry]:
    """Load the corpus file at `path`. Raises CorpusError listing every schema error; only a
    file that passes the schema gets the checks the schema cannot express."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CorpusError(path, [f"not valid JSON: {e}"]) from e

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    problems = _schema_problems(data, validator.iter_errors(data))
    if problems:
        raise CorpusError(path, problems)

    problems = _name_problems(data)
    if problems:
        raise CorpusError(path, problems)

    return [_entry(item) for item in data]


def _entry_label(data: Any, index: int) -> str:
    """How a problem line names an entry: `entry 3 (蚵仔煎)`, or `entry 3` when the entry has no
    usable official name (missing, empty, or not a string)."""
    name = data[index].get("official_name") if isinstance(data[index], dict) else None
    if isinstance(name, str) and name:
        return f"entry {index} ({name})"
    return f"entry {index}"


def _schema_problems(data: Any, errors: Iterable[ValidationError]) -> list[str]:
    """Turn jsonschema's errors into problem lines, `entry N (name), field X: reason`, in the
    order jsonschema reports them. An error about the file as a whole is labelled `corpus`."""
    problems: dict[str, None] = {}  # ordered set: `required` yields one error per missing key
    for error in errors:
        path = list(error.absolute_path)
        if not path or not isinstance(path[0], int):
            label, prefix = "corpus", ""
        else:
            label = _entry_label(data, path[0])
            prefix = ".".join(p for p in path[1:] if isinstance(p, str))
        for field, message in _field_messages(error, prefix):
            where = f"{label}, field {field}" if field else label
            problems[f"{where}: {message}"] = None
    return list(problems)


def _field_messages(error: ValidationError, prefix: str) -> list[tuple[str, str]]:
    """The field and reason for one schema error; `prefix` is the field path the error sits at
    (`attributes.flavor`). A missing or unknown field is named by its own key, since jsonschema
    reports it at the parent object. An error from the drink rule (the schema's if/then/else)
    says which way Dish type made it fail."""

    def join(key: str) -> str:
        return f"{prefix}.{key}" if prefix else key

    instance: Any = error.instance
    if error.validator == "required":
        required: Any = error.validator_value
        missing = [k for k in required if k not in instance]
        return [(join(k), "missing field") for k in missing]
    if error.validator == "additionalProperties":
        schema: Any = error.schema
        known = schema.get("properties", {})
        unknown = [k for k in instance if k not in known]
        return [(join(k), "unknown field") for k in unknown]
    if error.validator == "type" and not error.absolute_path:
        # jsonschema's message would print the whole file.
        return [("", f"the file holds {_json_kind(instance)}, not an array of entries")]
    message = error.message
    if "then" in error.absolute_schema_path:
        message = f"Dish type is Drink, so Physical form must be a drink value: {message}"
    elif "else" in error.absolute_schema_path:
        message = f"Dish type is not Drink, so Physical form must not be a drink value: {message}"
    return [(prefix, message)]


def _json_kind(value: Any) -> str:
    if isinstance(value, dict):
        return "an object"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "a string"
    return "null"


def _name_problems(data: list[dict[str, Any]]) -> list[str]:
    """The checks the schema cannot express: no alias equals its entry's official name; no name
    (official name or alias) belongs to two entries, since distractors are looked up by official
    name [R17] and a guess of one entry must not count as correct for another [R20]. A shared
    name is reported at the later entry. Names are compared after the normalization [R22]; a
    name empty after it is reported as such and left out of the other checks."""
    problems = []
    # normalized name -> (the first entry holding it, "the official name" or "an alias")
    first_seen: dict[str, tuple[int, str]] = {}
    for index, item in enumerate(data):
        label = _entry_label(data, index)
        official = normalize(item["official_name"])
        names = [("official_name", item["official_name"], official, "the official name")]
        names += [("aliases", alias, normalize(alias), "an alias") for alias in item["aliases"]]
        for field, name, key, _ in names:
            if not key:
                problems.append(f"{label}, field {field}: {name!r} is empty after normalization")
            elif field == "aliases" and key == official:
                problems.append(f"{label}, field aliases: alias {name!r} equals the official name")
            elif key in first_seen:
                other, role = first_seen[key]
                problems.append(
                    f"{label}, field {field}: {name!r} is also {role} of "
                    f"{_entry_label(data, other)}"
                )
        for _, _, key, role in names:
            if key:
                first_seen.setdefault(key, (index, role))
    return problems


def _entry(item: dict[str, Any]) -> CorpusEntry:
    """Copy one validated entry into a typed, immutable CorpusEntry; lists become tuples."""
    attributes = item["attributes"]
    return CorpusEntry(
        official_name=item["official_name"],
        aliases=tuple(item["aliases"]),
        english_names=tuple(item["english_names"]),
        forbidden_words=tuple(item["forbidden_words"]),
        attributes=Attributes(
            dish_type=tuple(attributes["dish_type"]),
            main_ingredients=tuple(attributes["main_ingredients"]),
            cooking_method=tuple(attributes["cooking_method"]),
            flavor=tuple(attributes["flavor"]),
            physical_form=tuple(attributes["physical_form"]),
            occasion=tuple(attributes["occasion"]),
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="load-corpus", description="Load a corpus file and print its entry count."
    )
    parser.add_argument("corpus", type=Path, help="path to the corpus JSON file")
    args = parser.parse_args(argv)
    try:
        entries = load_corpus(args.corpus)
    except (CorpusError, OSError) as e:
        print(e, file=sys.stderr)
        return 1
    print(len(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
