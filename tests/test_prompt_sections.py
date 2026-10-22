"""The shared `=== name ===` parser of the prompt files (T10 F3)."""

from pathlib import Path

import pytest

from dont_say_oyster.cards import REPO_ROOT
from dont_say_oyster.prompt_sections import sections


def _file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "role.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_sections_are_split_at_headers_and_stripped(tmp_path: Path) -> None:
    path = _file(
        tmp_path,
        "=== prompt ===\n\nLine one.\n  Line two.\n\n=== fixed message [R11] ===  \nTry again.\n",
    )
    assert sections(path) == {
        "prompt": "Line one.\n  Line two.",
        "fixed message [R11]": "Try again.",
    }


def test_text_before_the_first_header_is_ignored(tmp_path: Path) -> None:
    path = _file(tmp_path, "A note for nobody.\n=== prompt ===\nHello.")
    assert sections(path) == {"prompt": "Hello."}


def test_a_line_that_only_looks_like_a_header_is_text(tmp_path: Path) -> None:
    path = _file(tmp_path, "=== prompt ===\nSee === this === below.\n==== x ====\n")
    assert sections(path) == {"prompt": "See === this === below.\n==== x ===="}


def test_a_repeated_header_raises_naming_the_file_and_the_section(tmp_path: Path) -> None:
    path = _file(tmp_path, "=== prompt ===\nOne.\n=== prompt ===\nTwo.\n")
    with pytest.raises(ValueError, match=r"role\.txt repeats the section 'prompt'"):
        sections(path)


def test_a_missing_section_raises_naming_the_file_and_the_section(tmp_path: Path) -> None:
    path = _file(tmp_path, "=== prompt ===\nx\n=== task: description ===\ny\n")
    with pytest.raises(ValueError, match=r"role\.txt has no section 'fixed message \[R11\]'"):
        sections(path)["fixed message [R11]"]


def test_a_file_is_read_once_per_path(tmp_path: Path) -> None:
    path = _file(tmp_path, "=== prompt ===\nFirst.\n")
    first = sections(path)
    path.write_text("=== prompt ===\nSecond.\n", encoding="utf-8")
    assert sections(path) is first
    assert first["prompt"] == "First."


@pytest.mark.parametrize(
    ("role", "names"),
    [
        ("describer", ["prompt", "task: description", "task: answer", "fixed message [R11]",
                       "conventions"]),
        ("challenger", ["prompt", "re-ask [R40]", "fixed message [R40]", "conventions"]),
        ("guesser", ["prompt", "task: question or guess", "task: guess only",
                     "fixed message [R17]", "blocked lookup result", "conventions"]),
    ],
)
def test_the_committed_prompt_files_parse(role: str, names: list[str]) -> None:
    assert list(sections(REPO_ROOT / "prompts" / f"{role}.txt")) == names
