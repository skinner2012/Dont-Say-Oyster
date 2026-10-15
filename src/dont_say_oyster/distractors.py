"""Distractor picker: asks a model which corpus entries a description of a card could also
point to, keeps the valid picks, and writes the distractor file. Run as
`uv run pick-distractors CORPUS DISTRACTORS --names NAMES` for a full run, or with
`--repick NAME ...` to run a new round for those names only.

The distractor file is a JSON object keyed by official name, in the order the names were
given. Each value holds `rounds` (numbered from 1; each round's `kept` picks, its `dropped`
picks with their reasons, and `invalid_reply`: null, or the raw reply when it was not a JSON
array of strings) and `current`, the list the author reviews and may edit by hand and the list
the cards are built from. A round sets `current` to its kept picks. Read the file only through
`load_distractors`."""

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from dont_say_oyster.corpus import CorpusEntry, CorpusError, load_corpus

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "distractors.txt"
MODEL = "claude-opus-5-5"
# Thinking tokens count against max_tokens; the reply streams, so a large cap is safe.
MAX_TOKENS = 64000
MAX_DISTRACTORS = 5

Ask = Callable[[str], str]
"""Sends one prompt to the model and returns the reply text."""


@dataclass(frozen=True)
class DroppedPick:
    pick: str
    reason: str


@dataclass(frozen=True)
class PickRound:
    round: int
    kept: tuple[str, ...]
    dropped: tuple[DroppedPick, ...]
    invalid_reply: str | None


@dataclass(frozen=True)
class DistractorRecord:
    rounds: tuple[PickRound, ...]
    current: tuple[str, ...]


class DistractorFileError(Exception):
    """The distractor file cannot be loaded. `problems` holds one line per error."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"{path}:\n" + "\n".join(f"  {p}" for p in problems))
        self.problems = problems


class PickError(Exception):
    """The pick command cannot run with the names it was given."""


_STRINGS = {"type": "array", "items": {"type": "string"}}
_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {
        "type": "object",
        "required": ["rounds", "current"],
        "additionalProperties": False,
        "properties": {
            "rounds": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["round", "kept", "dropped", "invalid_reply"],
                    "additionalProperties": False,
                    "properties": {
                        "round": {"type": "integer"},
                        "kept": _STRINGS,
                        "dropped": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["pick", "reason"],
                                "additionalProperties": False,
                                "properties": {
                                    "pick": {"type": "string"},
                                    "reason": {"type": "string"},
                                },
                            },
                        },
                        "invalid_reply": {"type": ["string", "null"]},
                    },
                },
            },
            "current": _STRINGS,
        },
    },
}


def load_distractors(path: Path) -> dict[str, DistractorRecord]:
    """Load the distractor file at `path`, keyed by official name in file order. Raises
    DistractorFileError when the file is not valid JSON, does not have the shape described in
    this module's docstring, or a name's rounds are not numbered 1, 2, 3, ..."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise DistractorFileError(path, [f"not valid JSON: {e}"]) from e

    problems = []
    for error in Draft202012Validator(_FILE_SCHEMA).iter_errors(data):
        where = "/".join(str(p) for p in error.absolute_path)
        if not where:
            problems.append("the file must be a JSON object keyed by official name")
        else:
            problems.append(f"{where}: {error.message}")
    if problems:
        raise DistractorFileError(path, problems)

    for name, record in data.items():
        numbers = [r["round"] for r in record["rounds"]]
        if numbers != list(range(1, len(numbers) + 1)):
            problems.append(f"{name}/rounds: rounds are numbered {numbers}, not 1, 2, 3, ...")
    if problems:
        raise DistractorFileError(path, problems)

    return {name: _record(record) for name, record in data.items()}


def _record(record: dict[str, Any]) -> DistractorRecord:
    return DistractorRecord(
        rounds=tuple(
            PickRound(
                round=r["round"],
                kept=tuple(r["kept"]),
                dropped=tuple(DroppedPick(d["pick"], d["reason"]) for d in r["dropped"]),
                invalid_reply=r["invalid_reply"],
            )
            for r in record["rounds"]
        ),
        current=tuple(record["current"]),
    )


def write_distractors(path: Path, records: dict[str, DistractorRecord]) -> None:
    """Write the distractor file, replacing it in one step so a crash never leaves half a
    file."""
    data = {name: asdict(record) for name, record in records.items()}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def build_prompt(template: str, target: CorpusEntry, corpus: Sequence[CorpusEntry]) -> str:
    """Fill the prompt: `{target}` is the target's whole entry, `{others}` every other entry's
    official name, English names, and attributes, both as JSON."""
    others = [
        {
            "official_name": e.official_name,
            "english_names": list(e.english_names),
            "attributes": asdict(e.attributes),
        }
        for e in corpus
        if e.official_name != target.official_name
    ]
    return template.replace(
        "{target}", json.dumps(asdict(target), ensure_ascii=False)
    ).replace("{others}", json.dumps(others, ensure_ascii=False))


def parse_reply(reply: str) -> list[str] | None:
    """The reply's picks, or None when the reply is not a JSON array of strings."""
    try:
        data = json.loads(reply)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list) or not all(isinstance(p, str) for p in data):
        return None
    return data


def sort_picks(
    target: str, picks: Sequence[str], corpus: Sequence[CorpusEntry]
) -> tuple[tuple[str, ...], tuple[DroppedPick, ...]]:
    """Keep the first five picks that are the official name of another entry (exact string);
    every other pick is dropped with its reason."""
    official = {e.official_name for e in corpus}
    alias_of = {alias: e.official_name for e in corpus for alias in e.aliases}
    kept: list[str] = []
    dropped: list[DroppedPick] = []
    seen: set[str] = set()
    for pick in picks:
        if pick in seen:
            reason = "repeats an earlier pick"
        elif pick == target:
            reason = "the card itself"
        elif pick in alias_of:
            reason = f"an alias of {alias_of[pick]}, not an official name"
        elif pick not in official:
            reason = "not a name in the corpus"
        elif len(kept) >= MAX_DISTRACTORS:
            reason = f"over the limit of {MAX_DISTRACTORS}"
        else:
            reason = ""
        seen.add(pick)
        if reason:
            dropped.append(DroppedPick(pick, reason))
        else:
            kept.append(pick)
    return tuple(kept), tuple(dropped)


def pick_round(
    target: CorpusEntry,
    corpus: Sequence[CorpusEntry],
    template: str,
    ask: Ask,
    number: int,
) -> PickRound:
    """Ask the model once for `target`'s distractors and sort its reply into round `number`."""
    reply = ask(build_prompt(template, target, corpus))
    picks = parse_reply(reply)
    if picks is None:
        return PickRound(number, (), (), invalid_reply=reply)
    kept, dropped = sort_picks(target.official_name, picks, corpus)
    return PickRound(number, kept, dropped, invalid_reply=None)


def run_pick(
    corpus: Sequence[CorpusEntry],
    names: Sequence[str],
    out: Path,
    template: str,
    ask: Ask,
    *,
    repick: bool,
) -> None:
    """A full run (`repick` false) starts a fresh distractor file holding `names`; a re-pick
    adds a round for `names` only and leaves every other name as it is. Every name is checked
    before the first model call; the file is written after each name, so a failed call keeps
    the names already done."""
    by_name = {e.official_name: e for e in corpus}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise PickError(f"not an official name in the corpus: {', '.join(unknown)}")
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise PickError(f"named more than once: {', '.join(repeated)}")

    records: dict[str, DistractorRecord] = {}
    if repick:
        records = load_distractors(out)
        missing = [n for n in names if n not in records]
        if missing:
            raise PickError(f"not in the distractor file: {', '.join(missing)}")

    for name in names:
        earlier = records[name].rounds if name in records else ()
        new = pick_round(by_name[name], corpus, template, ask, len(earlier) + 1)
        records[name] = DistractorRecord(rounds=(*earlier, new), current=new.kept)
        write_distractors(out, records)
        status = "reply was not a JSON array of strings" if new.invalid_reply is not None else (
            f"kept {len(new.kept)}, dropped {len(new.dropped)}"
        )
        print(f"{name}: round {new.round}, {status}", file=sys.stderr)


def model_ask() -> Ask:
    """The real model call: Claude through langchain-anthropic, adaptive thinking. The key is
    ANTHROPIC_API_KEY, read from `.env` when it is not already in the environment."""
    from dotenv import load_dotenv
    from langchain_anthropic import ChatAnthropic

    load_dotenv()
    llm = ChatAnthropic(  # type: ignore[call-arg]
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        streaming=True,
    )

    def ask(prompt: str) -> str:
        return llm.invoke(prompt).text

    return ask


def main(argv: Sequence[str] | None = None, ask: Ask | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pick-distractors",
        description="Pick distractors for official names and write the distractor file.",
    )
    parser.add_argument("corpus", type=Path, help="path to the corpus JSON file")
    parser.add_argument("distractors", type=Path, help="path to the distractor file")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--names",
        type=Path,
        help="JSON array of official names; starts a fresh distractor file",
    )
    mode.add_argument(
        "--repick",
        nargs="+",
        metavar="NAME",
        help="run a new round for these names only, keeping every other name as it is",
    )
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.corpus)
        template = PROMPT_PATH.read_text(encoding="utf-8")
        for placeholder in ("{target}", "{others}"):
            if placeholder not in template:
                raise PickError(f"{PROMPT_PATH}: the prompt has no {placeholder}")
        if args.repick:
            names = list(args.repick)
        else:
            names = json.loads(args.names.read_text(encoding="utf-8"))
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise PickError(f"{args.names}: not a JSON array of official names")
        run_pick(
            corpus,
            names,
            args.distractors,
            template,
            ask or model_ask(),
            repick=bool(args.repick),
        )
    except (CorpusError, DistractorFileError, PickError, OSError, json.JSONDecodeError) as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
