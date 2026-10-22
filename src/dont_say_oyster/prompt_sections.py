"""The `=== name ===` sections of the author's prompt files (`prompts/*.txt`), one parser for
every role (T10 F3). A header is a line `=== name ===`, trailing whitespace allowed; a section's
text runs to the next header and is stripped of surrounding whitespace; text before the first
header is ignored. Each file is read once per path."""

import re
from functools import cache
from pathlib import Path

_HEADER = re.compile(r"=== (.+) ===")


class Sections(dict[str, str]):
    """A prompt file's sections by name. Looking up a section the file lacks raises ValueError
    naming the file and the section. Shared by every caller of `sections`; do not mutate."""

    def __init__(self, path: Path, found: dict[str, str]) -> None:
        super().__init__(found)
        self.path = path

    def __missing__(self, name: str) -> str:
        raise ValueError(f"prompt file {self.path} has no section {name!r}")


@cache
def sections(path: Path) -> Sections:
    """The sections of the prompt file at `path`. Raises ValueError when a header repeats."""
    found: dict[str, list[str]] = {}
    lines: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        header = _HEADER.fullmatch(line.rstrip())
        if header is None:
            if lines is not None:
                lines.append(line)
            continue
        name = header.group(1)
        if name in found:
            raise ValueError(f"prompt file {path} repeats the section {name!r}")
        lines = found[name] = []
    return Sections(path, {name: "\n".join(body).strip() for name, body in found.items()})
