"""Cross-game memory files (`SPEC.md` Cross-game memory definition, Storage): each role has its
own JSON memory file per game, `<directory>/<role>-<nn>.json` (`describer-07.json`), in the format
of `data/memory/schema.json`. Game 1 starts from the empty memory, since each batch starts from
empty memory, and reads no file; game n > 1 reads only game n - 1's file. The size limit (the
latest five entries in full, plus one rolling summary) is kept by `advance`, and the schema
refuses a file over it. `render` is the one place the memory block is formatted, so every prompt
that shows memory, and the memory token count, see the same text. Language and content checks
on an entry ([R6], the Check rule) are not made here."""

import json
from pathlib import Path
from typing import Any, Literal, TypedDict

from jsonschema import Draft202012Validator

# The package is installed editable from the repo, so the schema is found next to it.
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "memory" / "schema.json"
LATEST = 5  # entries kept in full (the size limit)
NONE = "(none)"

Role = Literal["describer", "guesser"]


class Entry(TypedDict):
    game: int
    text: str


class Memory(TypedDict):
    """One role's memory: the latest entries in ascending game order, at most five, and the
    rolling summary of the older entries, or None until there is one."""

    entries: list[Entry]
    summary: str | None


class MemoryFileError(Exception):
    """A memory file a game needs is missing or invalid; the message names the path."""

    def __init__(self, path: Path, problem: str) -> None:
        super().__init__(f"{path}: {problem}")
        self.path = path


def empty_memory() -> Memory:
    """The memory a batch starts from."""
    return {"entries": [], "summary": None}


def memory_path(directory: Path, role: Role, game: int) -> Path:
    """The file of `role` written after game `game`."""
    return directory / f"{role}-{game:02d}.json"


def read_memory(directory: Path, role: Role, game: int) -> Memory:
    """The memory `role` starts game `game` with: the empty memory for game 1, with no file read;
    otherwise game `game` - 1's file. Raises MemoryFileError naming the path when that file is
    missing, not valid JSON, not valid against the schema, or does not belong to its name (another
    role or game, entries out of order or after the file's game), so a game never starts from
    empty memory by accident."""
    if game < 1:
        raise ValueError(f"game numbers start at 1, not {game}")
    if game == 1:
        return empty_memory()
    previous = game - 1
    path = memory_path(directory, role, previous)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise MemoryFileError(path, "missing") from e
    except json.JSONDecodeError as e:
        raise MemoryFileError(path, f"not valid JSON: {e}") from e
    _check(path, data, role, previous)
    return {"entries": data["entries"], "summary": data["summary"]}


def write_memory(directory: Path, role: Role, game: int, memory: Memory) -> Path:
    """Write `memory` as the file of `role` after game `game`, creating `directory` if needed,
    and return the file's path. Raises MemoryFileError, writing nothing, when the file would not
    be valid."""
    path = memory_path(directory, role, game)
    data = {"role": role, "game": game, "entries": memory["entries"],
            "summary": memory["summary"]}
    _check(path, data, role, game)
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def advance(memory: Memory, game: int, entry: str, summary: str | None) -> Memory:
    """`memory` after game `game`'s entry: the entry appended, the oldest dropped beyond the
    latest five, and the summary replaced when `summary` is given (kept when it is None). Raises
    ValueError when `game` is not after the last entry's game."""
    entries = memory["entries"]
    if entries and game <= entries[-1]["game"]:
        raise ValueError(f"game {game} is not after the last entry's game {entries[-1]['game']}")
    new: Entry = {"game": game, "text": entry}
    return {
        "entries": [*entries, new][-LATEST:],
        "summary": memory["summary"] if summary is None else summary,
    }


def render(memory: Memory) -> str:
    """The memory block the prompts show and the memory token count measures: each entry with
    its game number, then the rolling summary; an empty part shows (none)."""
    entries = "\n".join(f"Game {e['game']}: {e['text']}" for e in memory["entries"]) or NONE
    summary = memory["summary"] if memory["summary"] is not None else NONE
    return f"Latest entries:\n{entries}\nSummary of older games:\n{summary}"


def _check(path: Path, data: Any, role: Role, game: int) -> None:
    """Raise MemoryFileError naming `path` unless `data` is valid against the schema and is the
    file of `role` after game `game`, its entries in ascending game order and none after it."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e.absolute_path) or 'file'}: {e.message}" for e in errors
        )
        raise MemoryFileError(path, problems)
    if data["role"] != role or data["game"] != game:
        raise MemoryFileError(
            path, f"holds {data['role']} after game {data['game']}, not {role} after game {game}"
        )
    games = [e["game"] for e in data["entries"]]
    if games != sorted(set(games)) or any(g > game for g in games):
        raise MemoryFileError(path, f"entry games {games} are not ascending up to game {game}")
