"""The data test: loads the committed corpus, cards file, and manifests, so every commit that
touches them is checked by the normal test command. The corpus part skips only while the corpus
file is absent (before T4); the card part skips only while the cards file and all four manifests
are absent (before T8), and fails when some are present and some are not."""

import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from dont_say_oyster import cards
from dont_say_oyster.cards import CARDS_PATH, check_manifests, load_cards, manifest_paths
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.selection import main as selection_command
from tests import card_fixtures as fx

CORPUS_PATH = cards.REPO_ROOT / "data" / "corpus" / "corpus.json"


def check_corpus(corpus: Path) -> None:
    if not corpus.exists():
        pytest.skip(f"{corpus} is absent (before T4)")
    load_corpus(corpus)


def check_cards(corpus: Path, cards_path: Path, manifests: Sequence[Path]) -> None:
    files = [cards_path, *manifests]
    present = [p for p in files if p.exists()]
    if not present:
        pytest.skip(f"the cards file and the four manifests are absent (before T8): {cards_path}")
    if len(present) != len(files):
        absent = [str(p) for p in files if not p.exists()]
        pytest.fail(f"some card files are present and some are absent: {', '.join(absent)}")
    load_cards(cards_path, load_corpus(corpus))
    check_manifests(manifests, cards_path)


def test_committed_corpus_loads() -> None:
    check_corpus(CORPUS_PATH)


def test_committed_cards_and_manifests_load_and_match() -> None:
    check_cards(CORPUS_PATH, CARDS_PATH, manifest_paths())


# The card part's behaviour, on fixture files.


@pytest.fixture
def card_files(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    """A fixture corpus, the cards and manifests built from it, and their paths."""
    corpus = fx.write_corpus(tmp_path / "corpus.json")
    selection = tmp_path / "selection.json"
    assert selection_command([str(corpus), str(selection)]) == 0
    distractors = fx.write_distractor_file(tmp_path / "distractors.json")
    cards_path, batches = tmp_path / "cards.json", tmp_path / "batches"
    args = [str(corpus), str(selection), str(distractors), str(cards_path), str(batches)]
    assert cards.main(args) == 0
    return corpus, cards_path, manifest_paths(batches)


def test_card_part_skips_with_its_reason_while_all_card_files_are_absent(
    card_files: tuple[Path, Path, list[Path]],
) -> None:
    corpus, cards_path, manifests = card_files
    cards_path.unlink()
    shutil.rmtree(manifests[0].parents[1])
    with pytest.raises(pytest.skip.Exception, match="absent \\(before T8\\)"):
        check_cards(corpus, cards_path, manifests)


@pytest.mark.parametrize("remove", ["cards", "one_manifest"])
def test_card_part_fails_when_only_some_card_files_are_present(
    card_files: tuple[Path, Path, list[Path]], remove: str
) -> None:
    corpus, cards_path, manifests = card_files
    gone = cards_path if remove == "cards" else manifests[1]
    gone.unlink()
    with pytest.raises(pytest.fail.Exception, match=str(gone)):
        check_cards(corpus, cards_path, manifests)


def test_card_part_passes_on_built_files(card_files: tuple[Path, Path, list[Path]]) -> None:
    check_cards(*card_files)


def test_card_part_fails_on_a_changed_manifest(
    card_files: tuple[Path, Path, list[Path]],
) -> None:
    corpus, cards_path, manifests = card_files
    data = json.loads(manifests[3].read_text(encoding="utf-8"))
    data["card_ids"].reverse()
    manifests[3].write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(cards.ManifestError):
        check_cards(corpus, cards_path, manifests)


def test_corpus_part_skips_with_its_reason_while_the_corpus_is_absent(tmp_path: Path) -> None:
    with pytest.raises(pytest.skip.Exception, match="absent \\(before T4\\)"):
        check_corpus(tmp_path / "corpus.json")
