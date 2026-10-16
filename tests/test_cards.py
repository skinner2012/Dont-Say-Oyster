"""Card selection, the card builder, the card loader, and the manifest check, run on the
generated fixture corpus and fixture distractor file in tests/card_fixtures.py."""

import hashlib
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dont_say_oyster import cards, selection
from dont_say_oyster.cards import (
    CardFileError,
    ManifestError,
    card_id,
    check_manifests,
    load_cards,
    manifest_paths,
)
from dont_say_oyster.corpus import CorpusEntry, load_corpus
from dont_say_oyster.distractors import DistractorRecord, write_distractors
from dont_say_oyster.selection import (
    GROUPS,
    SelectionError,
    attribute_key,
    draw,
    group_index,
    order,
    quotas,
    round_robin,
)
from tests import card_fixtures as fx


@pytest.fixture
def corpus_path(tmp_path: Path) -> Path:
    return fx.write_corpus(tmp_path / "corpus.json")


@pytest.fixture
def corpus(corpus_path: Path) -> list[CorpusEntry]:
    return load_corpus(corpus_path)


def run_select(corpus_path: Path, out: Path) -> list[str]:
    assert selection.main([str(corpus_path), str(out)]) == 0
    names: list[str] = json.loads(out.read_text(encoding="utf-8"))
    return names


def run_build(tmp_path: Path, corpus_path: Path, sub: str = "build") -> tuple[Path, Path]:
    """Select, then build into tmp_path/sub; returns the cards file and the batches directory."""
    root = tmp_path / sub
    root.mkdir()
    selection_path = root / "selection.json"
    run_select(corpus_path, selection_path)
    distractors = fx.write_distractor_file(root / "distractors.json")
    cards_path, batches = root / "cards.json", root / "batches"
    code = cards.main(
        [str(corpus_path), str(selection_path), str(distractors), str(cards_path), str(batches)]
    )
    assert code == 0
    return cards_path, batches


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# Selection criterion


def test_quotas_on_the_corpus_at_2d8029c_are_the_ones_the_ticket_states() -> None:
    # Group sizes of data/corpus/corpus.json at 2d8029c. Dessert soup and Drink smooth tie for
    # the last card (both have 21 entries); the group listed first gets it.
    sizes = [43, 27, 85, 16, 37, 69, 21, 15, 21, 8]
    assert quotas(sizes) == [5, 3, 10, 2, 4, 8, 3, 2, 2, 1]


def test_quota_ties_go_to_the_group_listed_first() -> None:
    assert quotas([1, 1, 1], total=2) == [1, 1, 0]
    assert quotas([2, 1, 1], total=2) == [1, 1, 0]


def test_fixture_corpus_fills_every_group(corpus: list[CorpusEntry]) -> None:
    assert len(corpus) >= 41
    sizes = [0] * len(GROUPS)
    for entry in corpus:
        sizes[group_index(entry)] += 1
    assert sizes == [n for _, _, n in fx.GROUP_SHAPES]
    assert all(sizes)


def test_round_robin_skips_groups_with_no_items_left() -> None:
    groups = [["a1", "a2", "a3"], ["b1"], [], ["c1", "c2"]]
    assert round_robin(groups) == ["a1", "b1", "c1", "a2", "c2", "a3"]


def test_select_writes_forty_names_and_a_second_run_writes_the_same(
    tmp_path: Path, corpus_path: Path
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    names = run_select(corpus_path, first)
    run_select(corpus_path, second)
    assert len(names) == 40
    assert len(set(names)) == 40
    assert first.read_bytes() == second.read_bytes()


def test_select_follows_the_criteria_as_written(
    tmp_path: Path, corpus_path: Path, corpus: list[CorpusEntry]
) -> None:
    """Replays T7's selection and ordering criteria step by step and compares."""
    pools: list[list[CorpusEntry]] = [[] for _ in GROUPS]
    for entry in corpus:  # corpus file order
        pools[group_index(entry)].append(entry)
    rng = random.Random(2026)
    drawn: list[CorpusEntry] = []
    by_group: list[list[str]] = []
    rejected = 0
    for pool, quota in zip(pools, quotas([len(p) for p in pools]), strict=True):
        group: list[str] = []
        while len(group) < quota:
            entry = pool.pop(rng.randrange(len(pool)))
            if any(attribute_key(entry) == attribute_key(d) for d in drawn):
                rejected += 1
                continue
            drawn.append(entry)
            group.append(entry.official_name)
        by_group.append(group)
    expected = []
    for i in range(max(len(g) for g in by_group)):
        expected += [g[i] for g in by_group if i < len(g)]

    assert rejected > 0, "the fixture should make the draw reject a card"
    assert run_select(corpus_path, tmp_path / "selection.json") == expected


def test_selected_cards_differ_in_their_five_attribute_fields(
    tmp_path: Path, corpus_path: Path, corpus: list[CorpusEntry]
) -> None:
    by_name = {e.official_name: e for e in corpus}
    names = run_select(corpus_path, tmp_path / "selection.json")
    keys = {attribute_key(by_name[n]) for n in names}
    assert len(keys) == 40
    same = {fx.official_name(sum(n for _, _, n in fx.GROUP_SHAPES[:fx.SNACK_DRY]) + i)
            for i in fx.SAME_ATTRIBUTES}
    assert len(same & set(names)) <= 1


def test_attribute_fields_compare_as_sets_and_ignore_occasion(
    corpus: list[CorpusEntry],
) -> None:
    from dataclasses import replace

    entry = corpus[0]
    flipped = replace(
        entry,
        attributes=replace(
            entry.attributes,
            main_ingredients=("Pork", "Rice"),
            occasion=("Festival",),
        ),
    )
    plain = replace(entry, attributes=replace(entry.attributes, main_ingredients=("Rice", "Pork")))
    assert attribute_key(flipped) == attribute_key(plain)


def test_order_of_the_selection_is_the_selection(
    tmp_path: Path, corpus_path: Path, corpus: list[CorpusEntry]
) -> None:
    names = run_select(corpus_path, tmp_path / "selection.json")
    assert order(names, corpus) == names
    assert order(list(reversed(names)), corpus) != names


def test_an_entry_in_no_group_is_an_error(tmp_path: Path) -> None:
    data = fx.corpus_data()
    data[0]["attributes"]["dish_type"] = ["Dessert"]
    data[0]["attributes"]["physical_form"] = ["Sauced"]
    path = tmp_path / "corpus.json"
    write(path, data)
    with pytest.raises(SelectionError, match="fit none of the ten groups"):
        draw(load_corpus(path))
    assert selection.main([str(path), str(tmp_path / "selection.json")]) == 1
    assert not (tmp_path / "selection.json").exists()


def test_a_group_that_runs_out_of_different_entries_is_an_error(tmp_path: Path) -> None:
    data = fx.corpus_data()
    # Every Meal entry takes the same five fields: only one can be drawn.
    for entry in data:
        if entry["attributes"]["dish_type"] == ["Meal"]:
            entry["attributes"]["main_ingredients"] = ["Rice"]
            entry["attributes"]["physical_form"] = ["Dry"]
    path = tmp_path / "corpus.json"
    write(path, data)
    with pytest.raises(SelectionError, match="Meal dry or sauced"):
        draw(load_corpus(path))


# Card id


def test_card_id_is_a_short_hash_of_the_official_name() -> None:
    digest = hashlib.sha256("蚵仔煎".encode()).hexdigest()
    assert card_id("蚵仔煎") == "card-" + digest[:8]
    assert card_id("蚵仔煎") != card_id("蚵仔麵線")


# Build


def test_build_writes_forty_cards_and_four_manifests_in_one_order(
    tmp_path: Path, corpus_path: Path, corpus: list[CorpusEntry]
) -> None:
    cards_path, batches = run_build(tmp_path, corpus_path)
    names = read(tmp_path / "build" / "selection.json")
    data = read(cards_path)
    by_name = {e["official_name"]: e for e in fx.corpus_data()}

    assert [c["official_name"] for c in data] == names
    for card in data:
        entry = by_name[card["official_name"]]
        assert set(card) == {*entry, "card_id", "distractors"}
        assert {k: card[k] for k in entry} == entry
        assert card["card_id"] == card_id(card["official_name"])
        assert card["distractors"] == list(fx.distractor_records()[entry["official_name"]].current)
    # The fixture's hand edits reach the cards: some current lists differ from their round.
    assert any(
        list(fx.distractor_records()[c["official_name"]].rounds[0].kept) != c["distractors"]
        for c in data
    )

    ids = [c["card_id"] for c in data]
    for variant, path in zip(cards.VARIANTS, manifest_paths(batches), strict=True):
        assert read(path) == {
            "variant": variant,
            "cards": cards_path.resolve().as_posix(),
            "card_ids": ids,
        }
    check_manifests(manifest_paths(batches), cards_path)
    assert len(load_cards(cards_path, corpus)) == 40


def test_a_second_build_gives_the_same_ids_in_the_same_order(
    tmp_path: Path, corpus_path: Path
) -> None:
    first_cards, first_batches = run_build(tmp_path, corpus_path, "first")
    second_cards, second_batches = run_build(tmp_path, corpus_path, "second")
    assert first_cards.read_bytes() == second_cards.read_bytes()
    for first, second in zip(
        manifest_paths(first_batches), manifest_paths(second_batches), strict=True
    ):
        assert read(first)["card_ids"] == read(second)["card_ids"]


def test_card_ids_do_not_depend_on_the_order(
    tmp_path: Path, corpus: list[CorpusEntry], corpus_path: Path
) -> None:
    names = run_select(corpus_path, tmp_path / "selection.json")
    records = fx.distractor_records()
    built = cards.build_cards(corpus, names, records)
    rebuilt = cards.build_cards(corpus, list(reversed(names)), records)
    assert {c["official_name"]: c["card_id"] for c in built} == {
        c["official_name"]: c["card_id"] for c in rebuilt
    }


def test_manifest_names_the_cards_file_relative_to_the_repo_root(tmp_path: Path) -> None:
    assert cards._path_ref(cards.CARDS_PATH) == "data/cards/cards.json"
    assert cards._path_ref(cards.REPO_ROOT / "data" / ".." / "data/cards/cards.json") == (
        "data/cards/cards.json"
    )
    outside = tmp_path / "cards.json"
    assert cards._path_ref(outside) == outside.resolve().as_posix()


def build_inputs(tmp_path: Path, corpus_path: Path) -> tuple[Path, Path]:
    selection_path = tmp_path / "selection.json"
    run_select(corpus_path, selection_path)
    return selection_path, fx.write_distractor_file(tmp_path / "distractors.json")


def build_fails(tmp_path: Path, corpus_path: Path, selection_path: Path, distractors: Path,
                capsys: pytest.CaptureFixture[str], message: str) -> None:
    cards_path, batches = tmp_path / "cards.json", tmp_path / "batches"
    args = [str(corpus_path), str(selection_path), str(distractors), str(cards_path),
            str(batches)]
    assert cards.main(args) == 1
    assert message in capsys.readouterr().err
    assert not cards_path.exists()
    assert not batches.exists()


def test_build_fails_on_a_name_missing_from_the_distractor_file(
    tmp_path: Path, corpus_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection_path, distractors = build_inputs(tmp_path, corpus_path)
    records = fx.distractor_records()
    missing = read(selection_path)[3]
    del records[missing]
    write_distractors(distractors, records)
    build_fails(tmp_path, corpus_path, selection_path, distractors, capsys,
                f"not in the distractor file: {missing}")


def test_build_fails_on_a_selection_name_not_in_the_corpus(
    tmp_path: Path, corpus_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection_path, distractors = build_inputs(tmp_path, corpus_path)
    write(selection_path, [*read(selection_path)[:39], "肉夾饃"])
    build_fails(tmp_path, corpus_path, selection_path, distractors, capsys,
                "not an official name in the corpus: 肉夾饃")


def test_build_fails_on_a_repeated_selection_name(
    tmp_path: Path, corpus_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection_path, distractors = build_inputs(tmp_path, corpus_path)
    names = read(selection_path)
    write(selection_path, [*names[:39], names[0]])
    build_fails(tmp_path, corpus_path, selection_path, distractors, capsys,
                f"named more than once in the selection: {names[0]}")


def test_build_fails_on_a_selection_that_is_not_forty_names(
    tmp_path: Path, corpus_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection_path, distractors = build_inputs(tmp_path, corpus_path)
    write(selection_path, read(selection_path)[:39])
    build_fails(tmp_path, corpus_path, selection_path, distractors, capsys,
                "holds 39 cards, not 40")


def test_build_fails_on_a_current_list_with_an_alias(
    tmp_path: Path, corpus_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection_path, distractors = build_inputs(tmp_path, corpus_path)
    records = fx.distractor_records()
    name = read(selection_path)[0]
    records[name] = DistractorRecord(records[name].rounds, ("測試別名05",))
    write_distractors(distractors, records)
    build_fails(tmp_path, corpus_path, selection_path, distractors, capsys,
                "distractor 測試別名05 is not the official name of a corpus entry")


# Manifest check


@pytest.fixture
def built(tmp_path: Path, corpus_path: Path) -> tuple[Path, list[Path]]:
    cards_path, batches = run_build(tmp_path, corpus_path)
    return cards_path, manifest_paths(batches)


def test_manifest_check_fails_when_one_manifest_order_is_changed(
    built: tuple[Path, list[Path]],
) -> None:
    cards_path, manifests = built
    data = read(manifests[2])
    data["card_ids"][0], data["card_ids"][1] = data["card_ids"][1], data["card_ids"][0]
    write(manifests[2], data)
    with pytest.raises(ManifestError, match="card order differs") as e:
        check_manifests(manifests, cards_path)
    assert all(str(manifests[2]) in p for p in e.value.problems)


def test_manifest_check_fails_when_a_card_is_removed_from_the_cards_file(
    built: tuple[Path, list[Path]],
) -> None:
    cards_path, manifests = built
    data = read(cards_path)
    removed = data.pop(7)["card_id"]
    write(cards_path, data)
    with pytest.raises(ManifestError, match=f"lists ids not in .*{removed}"):
        check_manifests(manifests, cards_path)


def test_manifest_check_fails_when_a_card_is_removed_from_every_manifest(
    built: tuple[Path, list[Path]],
) -> None:
    cards_path, manifests = built
    for path in manifests:
        data = read(path)
        removed = data["card_ids"].pop(7)
        write(path, data)
    with pytest.raises(ManifestError, match=f"does not list cards {removed}"):
        check_manifests(manifests, cards_path)


def test_manifest_check_fails_on_an_id_listed_twice(built: tuple[Path, list[Path]]) -> None:
    cards_path, manifests = built
    for path in manifests:
        data = read(path)
        data["card_ids"][7] = data["card_ids"][6]
        write(path, data)
    with pytest.raises(ManifestError, match="more times than it holds them"):
        check_manifests(manifests, cards_path)


# Card loader

Mutation = Callable[[list[dict[str, Any]]], None]


def _set(index: int, field: str, value: Any) -> Mutation:
    def mutate(data: list[dict[str, Any]]) -> None:
        data[index][field] = value

    return mutate


def _delete(index: int, field: str) -> Mutation:
    def mutate(data: list[dict[str, Any]]) -> None:
        del data[index][field]

    return mutate


def _delete_attribute(data: list[dict[str, Any]]) -> None:
    del data[4]["attributes"]["flavor"]


def _duplicate_id(data: list[dict[str, Any]]) -> None:
    data[5]["card_id"] = data[2]["card_id"]


def _remove_card(data: list[dict[str, Any]]) -> None:
    data.pop()


def _add_card(data: list[dict[str, Any]]) -> None:
    data.append({**data[0], "card_id": "card-extra"})


def _distractor_is_the_card(data: list[dict[str, Any]]) -> None:
    data[3]["distractors"] = [data[3]["official_name"]]


SIX = [fx.official_name(n) for n in range(6)]
# (id, mutation, the expected start of the problem line, a word of the reason)
LOADER_ERRORS: list[tuple[str, Mutation, str, str]] = [
    ("thirty_nine_cards", _remove_card, "holds 39 cards", "not 40"),
    ("forty_one_cards", _add_card, "holds 41 cards", "not 40"),
    ("missing_card_id", _delete(1, "card_id"), "card 1 (", "field card_id: missing field"),
    ("missing_distractors", _delete(1, "distractors"), "card 1 (", "distractors: missing"),
    ("missing_aliases", _delete(1, "aliases"), "card 1 (", "aliases: missing field"),
    ("missing_attribute", _delete_attribute, "card 4 (", "attributes.flavor: missing field"),
    ("duplicate_card_id", _duplicate_id, "card 2 (", "is on more than one card"),
    ("six_distractors", _set(0, "distractors", SIX), "card 0 (", "6 distractors"),
    ("duplicate_distractor", _set(0, "distractors", [SIX[1], SIX[1]]), "card 0 (", "2 times"),
    ("distractor_unknown", _set(0, "distractors", ["肉夾饃"]), "card 0 (", "not the official"),
    ("distractor_alias", _set(0, "distractors", ["測試別名01"]), "card 0 (", "not the official"),
    ("distractor_is_the_card", _distractor_is_the_card, "card 3 (", "is the card itself"),
]


@pytest.mark.parametrize(
    ("mutate", "where", "reason"),
    [e[1:] for e in LOADER_ERRORS],
    ids=[e[0] for e in LOADER_ERRORS],
)
def test_card_loader_fails_on_each_error(
    built: tuple[Path, list[Path]],
    corpus: list[CorpusEntry],
    mutate: Mutation,
    where: str,
    reason: str,
) -> None:
    cards_path, _ = built
    data = read(cards_path)
    mutate(data)
    write(cards_path, data)
    with pytest.raises(CardFileError) as e:
        load_cards(cards_path, corpus)
    assert any(p.startswith(where) and reason in p for p in e.value.problems), e.value.problems


def test_card_loader_reads_typed_cards(
    built: tuple[Path, list[Path]], corpus: list[CorpusEntry]
) -> None:
    cards_path, _ = built
    loaded = load_cards(cards_path, corpus)
    data = read(cards_path)
    assert [c.card_id for c in loaded] == [c["card_id"] for c in data]
    first = loaded[0]
    assert first.distractors == tuple(data[0]["distractors"])
    assert first.attributes.dish_type == tuple(data[0]["attributes"]["dish_type"])


def test_card_loader_fails_on_invalid_json(tmp_path: Path, corpus: list[CorpusEntry]) -> None:
    path = tmp_path / "cards.json"
    path.write_text("[", encoding="utf-8")
    with pytest.raises(CardFileError, match="not valid JSON"):
        load_cards(path, corpus)
