"""The data test: loads the committed corpus, cards file, and manifests, so every commit that
touches them is checked by the normal test command. The corpus part skips only while the corpus
file is absent (before it is committed). The card part loads the cards file, runs the manifest
check, reselects the forty names from the committed corpus, failing when the result differs from the
committed selection, and rebuilds the cards from the committed corpus, selection, and
distractor file, failing when the result differs from the committed cards file or manifests.
It skips only while the cards
file and all four manifests are absent (before they are built), and fails when some card files
(those five, the selection, and the distractor file) are present and some are not."""

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from dont_say_oyster import cards
from dont_say_oyster.cards import (
    CARDS_PATH,
    DISTRACTORS_PATH,
    SELECTION_PATH,
    build_cards,
    check_manifests,
    load_cards,
    manifest_data,
    manifest_paths,
)
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.distractors import DistractorRecord, load_distractors, write_distractors
from dont_say_oyster.selection import main as selection_command
from dont_say_oyster.selection import select
from tests import card_fixtures as fx

CORPUS_PATH = cards.REPO_ROOT / "data" / "corpus" / "corpus.json"


@dataclass(frozen=True)
class CardFiles:
    corpus: Path
    selection: Path
    distractors: Path
    cards: Path
    manifests: Sequence[Path]


COMMITTED = CardFiles(CORPUS_PATH, SELECTION_PATH, DISTRACTORS_PATH, CARDS_PATH, manifest_paths())


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_corpus(corpus: Path) -> None:
    if not corpus.exists():
        pytest.skip(f"{corpus} is absent (before T4)")
    load_corpus(corpus)


def check_cards(files: CardFiles) -> None:
    built = [files.cards, *files.manifests]
    if not any(p.exists() for p in built):
        pytest.skip(f"the cards file and the four manifests are absent (before T8): {files.cards}")
    absent = [str(p) for p in [files.selection, files.distractors, *built] if not p.exists()]
    if absent:
        pytest.fail(f"some card files are present and some are absent: {', '.join(absent)}")

    corpus = load_corpus(files.corpus)
    load_cards(files.cards, corpus)
    check_manifests(files.manifests, files.cards)

    if select(corpus) != read(files.selection):
        pytest.fail(
            f"{files.selection} differs from the selection that select draws from the committed "
            "corpus; rerun select, pick, and build (T8)"
        )

    rebuilt = build_cards(corpus, read(files.selection), load_distractors(files.distractors))
    committed = read(files.cards)
    for index, (new, old) in enumerate(zip(rebuilt, committed, strict=True)):
        if new != old:
            pytest.fail(
                f"{files.cards}: card {index} ({old.get('official_name')}) differs from the "
                "card rebuilt from the committed corpus, selection, and distractor file"
            )
    for path, new in zip(
        files.manifests, manifest_data(rebuilt, files.cards), strict=True
    ):
        if read(path) != new:
            pytest.fail(f"{path} differs from the manifest rebuilt from the committed files")


def test_committed_corpus_loads() -> None:
    check_corpus(CORPUS_PATH)


def test_committed_cards_and_manifests_load_and_match() -> None:
    check_cards(COMMITTED)


def test_committed_paths_are_the_ticket_file_names() -> None:
    root = cards.REPO_ROOT
    assert SELECTION_PATH == root / "data" / "cards" / "selection.json"
    assert DISTRACTORS_PATH == root / "data" / "cards" / "distractors.json"
    assert CARDS_PATH == root / "data" / "cards" / "cards.json"
    assert list(COMMITTED.manifests) == [
        root / "batches" / v / "manifest.json" for v in ("V0", "V1", "V2", "V3")
    ]


# The card part's behaviour, on fixture files.


@pytest.fixture
def card_files(tmp_path: Path) -> CardFiles:
    """A fixture corpus, selection, and distractor file, and the cards and manifests built from
    them."""
    corpus = fx.write_corpus(tmp_path / "corpus.json")
    selection = tmp_path / "selection.json"
    assert selection_command([str(corpus), str(selection)]) == 0
    distractors = fx.write_distractor_file(tmp_path / "distractors.json")
    cards_path, batches = tmp_path / "cards.json", tmp_path / "batches"
    args = [str(corpus), str(selection), str(distractors), str(cards_path), str(batches)]
    assert cards.main(args) == 0
    return CardFiles(corpus, selection, distractors, cards_path, manifest_paths(batches))


def test_card_part_passes_on_freshly_built_files(card_files: CardFiles) -> None:
    check_cards(card_files)


def test_card_part_skips_with_its_reason_while_all_card_files_are_absent(
    card_files: CardFiles,
) -> None:
    card_files.cards.unlink()
    shutil.rmtree(card_files.manifests[0].parents[1])
    with pytest.raises(pytest.skip.Exception, match="absent \\(before T8\\)"):
        check_cards(card_files)


@pytest.mark.parametrize("remove", ["cards", "one_manifest", "selection", "distractors"])
def test_card_part_fails_when_only_some_card_files_are_present(
    card_files: CardFiles, remove: str
) -> None:
    gone = {
        "cards": card_files.cards,
        "one_manifest": card_files.manifests[1],
        "selection": card_files.selection,
        "distractors": card_files.distractors,
    }[remove]
    gone.unlink()
    with pytest.raises(pytest.fail.Exception, match=str(gone)):
        check_cards(card_files)


def test_card_part_fails_on_a_changed_manifest(card_files: CardFiles) -> None:
    manifest = card_files.manifests[3]
    data = read(manifest)
    data["card_ids"].reverse()
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(cards.ManifestError):
        check_cards(card_files)


def test_card_part_fails_after_an_uncarded_entry_changes_group_in_the_corpus(
    card_files: CardFiles,
) -> None:
    """Moving any entry between groups changes the pools the draw runs on, so the committed
    selection is no longer what select produces, even though every card copy still matches."""
    selected = set(read(card_files.selection))
    corpus = read(card_files.corpus)
    entry = next(
        e
        for e in corpus
        if e["official_name"] not in selected and e["attributes"]["dish_type"] == ["Snack"]
    )
    entry["attributes"]["dish_type"] = ["Dessert"]
    entry["attributes"]["flavor"] = ["Sweet"]
    card_files.corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(pytest.fail.Exception, match="differs from the selection"):
        check_cards(card_files)


def test_card_part_fails_after_a_card_forbidden_words_change_in_the_corpus(
    card_files: CardFiles,
) -> None:
    name = read(card_files.selection)[5]
    corpus = read(card_files.corpus)
    entry = next(e for e in corpus if e["official_name"] == name)
    entry["forbidden_words"].append("changed")
    card_files.corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    index = [c["official_name"] for c in read(card_files.cards)].index(name)
    with pytest.raises(pytest.fail.Exception, match=f"card {index} \\({name}\\) differs"):
        check_cards(card_files)


def test_card_part_fails_after_a_current_list_changes_in_the_distractor_file(
    card_files: CardFiles,
) -> None:
    records = load_distractors(card_files.distractors)
    name = read(card_files.selection)[9]
    other = next(n for n in read(card_files.selection) if n != name)
    records[name] = DistractorRecord(records[name].rounds, (other,))
    assert records[name].current != fx.distractor_records()[name].current
    write_distractors(card_files.distractors, records)
    index = [c["official_name"] for c in read(card_files.cards)].index(name)
    with pytest.raises(pytest.fail.Exception, match=f"card {index} \\({name}\\) differs"):
        check_cards(card_files)


def test_card_part_fails_when_a_manifest_names_another_cards_file(card_files: CardFiles) -> None:
    manifest = card_files.manifests[0]
    data = read(manifest)
    data["cards"] = "elsewhere/cards.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(pytest.fail.Exception, match=f"{manifest} differs"):
        check_cards(card_files)


def test_corpus_part_skips_with_its_reason_while_the_corpus_is_absent(tmp_path: Path) -> None:
    with pytest.raises(pytest.skip.Exception, match="absent \\(before T4\\)"):
        check_corpus(tmp_path / "corpus.json")
