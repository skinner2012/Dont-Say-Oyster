"""Distractor picker: sorting picks, the distractor file and its loader, the pick command and
its re-pick option, all with scripted model replies."""

import json
from pathlib import Path

import pytest

from dont_say_oyster import distractors
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.distractors import (
    PROMPT_PATH,
    DistractorFileError,
    DroppedPick,
    build_prompt,
    load_distractors,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures" / "distractors"
CORPUS = FIXTURES / "corpus.json"
# The fixture corpus, in file order:
# 滷肉飯 焢肉飯 腿庫飯 火雞肉飯 鴨肉飯 鵝肉飯 燻鵝 鹽水鵝 油飯 筒仔米糕


class Scripted:
    """A stand-in for the model: returns the given replies in order and keeps the prompts."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0)


def names_file(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "names.json"
    path.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    return path


def pick(tmp_path: Path, names: list[str], ask: Scripted) -> tuple[int, Path]:
    out = tmp_path / "distractors.json"
    code = main([str(CORPUS), str(out), "--names", str(names_file(tmp_path, names))], ask=ask)
    return code, out


def test_prompt_file_is_at_the_prompts_location_with_both_placeholders() -> None:
    assert PROMPT_PATH == Path(__file__).resolve().parents[1] / "prompts" / "distractors.txt"
    template = PROMPT_PATH.read_text(encoding="utf-8")
    assert "{target}" in template
    assert "{others}" in template


def test_reply_keeps_first_five_valid_picks_and_drops_the_rest_with_reasons(
    tmp_path: Path,
) -> None:
    reply = ["滷肉飯", "肉夾饃", "焢肉飯", "焢肉飯", "腿庫飯", "火雞肉飯", "鴨肉飯"]
    reply += ["鵝肉飯", "燻鵝", "鹽水鵝"]
    code, out = pick(tmp_path, ["滷肉飯"], Scripted(json.dumps(reply, ensure_ascii=False)))
    assert code == 0
    record = load_distractors(out)["滷肉飯"]
    assert record.current == ("焢肉飯", "腿庫飯", "火雞肉飯", "鴨肉飯", "鵝肉飯")
    (only,) = record.rounds
    assert only.round == 1
    assert only.kept == record.current
    assert only.dropped == (
        DroppedPick("滷肉飯", "the card itself"),
        DroppedPick("肉夾饃", "not a name in the corpus"),
        DroppedPick("焢肉飯", "repeats an earlier pick"),
        DroppedPick("燻鵝", "over the limit of 5"),
        DroppedPick("鹽水鵝", "over the limit of 5"),
    )
    assert only.invalid_reply is None


def test_alias_pick_is_dropped_naming_its_entry(tmp_path: Path) -> None:
    code, out = pick(tmp_path, ["油飯"], Scripted('["魯肉飯", "筒仔米糕"]'))
    assert code == 0
    (only,) = load_distractors(out)["油飯"].rounds
    assert only.kept == ("筒仔米糕",)
    assert only.dropped == (DroppedPick("魯肉飯", "an alias of 滷肉飯, not an official name"),)


def test_empty_reply_gives_an_empty_current_list(tmp_path: Path) -> None:
    code, out = pick(tmp_path, ["滷肉飯"], Scripted("[]"))
    assert code == 0
    record = load_distractors(out)["滷肉飯"]
    assert record.current == ()
    assert record.rounds[0].kept == ()
    assert record.rounds[0].dropped == ()
    assert record.rounds[0].invalid_reply is None


@pytest.mark.parametrize(
    "reply", ["Here are the picks: 焢肉飯", '{"picks": ["焢肉飯"]}', '["焢肉飯", 3]', ""]
)
def test_reply_that_is_not_an_array_of_strings_is_zero_picks_and_the_run_continues(
    tmp_path: Path, reply: str
) -> None:
    code, out = pick(tmp_path, ["滷肉飯", "油飯"], Scripted(reply, '["筒仔米糕"]'))
    assert code == 0
    records = load_distractors(out)
    bad = records["滷肉飯"]
    assert bad.current == ()
    assert bad.rounds[0].kept == ()
    assert bad.rounds[0].dropped == ()
    assert bad.rounds[0].invalid_reply == reply
    assert records["油飯"].current == ("筒仔米糕",)


def test_prompt_holds_the_whole_target_entry_and_the_others_reduced(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS)
    template = "T={target}\nO={others}"
    prompt = build_prompt(template, corpus[0], corpus)
    target_line, others_line = prompt.split("\n")
    target = json.loads(target_line.removeprefix("T="))
    others = json.loads(others_line.removeprefix("O="))
    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert target == raw[0]
    assert [o["official_name"] for o in others] == [e["official_name"] for e in raw[1:]]
    for o, e in zip(others, raw[1:], strict=True):
        assert o == {k: e[k] for k in ("official_name", "english_names", "attributes")}
    assert "滷肉飯" in target_line  # Chinese is written as is, not as \u escapes


def test_command_sends_the_prompt_file_filled_in(tmp_path: Path) -> None:
    ask = Scripted("[]")
    pick(tmp_path, ["滷肉飯"], ask)
    (prompt,) = ask.prompts
    assert "{target}" not in prompt and "{others}" not in prompt
    first_line = PROMPT_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert prompt.startswith(first_line)


def test_repick_changes_only_the_named_name(tmp_path: Path) -> None:
    ask = Scripted('["焢肉飯", "腿庫飯"]', '["筒仔米糕"]', '["油飯", "鴨肉飯"]')
    code, out = pick(tmp_path, ["滷肉飯", "油飯", "筒仔米糕"], ask)
    assert code == 0

    # The author edits one name's current list by hand.
    data = json.loads(out.read_text(encoding="utf-8"))
    data["油飯"]["current"] = ["筒仔米糕", "滷肉飯"]
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    before = load_distractors(out)

    code = main([str(CORPUS), str(out), "--repick", "筒仔米糕"], ask=Scripted('["鵝肉飯"]'))
    assert code == 0
    after = load_distractors(out)

    assert list(after) == ["滷肉飯", "油飯", "筒仔米糕"]
    assert after["滷肉飯"] == before["滷肉飯"]
    assert after["油飯"] == before["油飯"]
    assert after["油飯"].current == ("筒仔米糕", "滷肉飯")
    repicked = after["筒仔米糕"]
    assert [r.round for r in repicked.rounds] == [1, 2]
    assert repicked.rounds[0] == before["筒仔米糕"].rounds[0]
    assert repicked.rounds[1].kept == ("鵝肉飯",)
    assert repicked.current == ("鵝肉飯",)


@pytest.mark.parametrize("name", ["肉夾饃", "鵝肉飯"])  # not in the corpus; not in the file
def test_repick_of_an_unknown_name_exits_non_zero_and_changes_nothing(
    tmp_path: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = pick(tmp_path, ["滷肉飯"], Scripted('["焢肉飯"]'))
    assert code == 0
    before = out.read_bytes()
    ask = Scripted()
    code = main([str(CORPUS), str(out), "--repick", "滷肉飯", name], ask=ask)
    assert code != 0
    assert name in capsys.readouterr().err
    assert ask.prompts == []
    assert out.read_bytes() == before


def test_repick_without_a_distractor_file_exits_non_zero(tmp_path: Path) -> None:
    code = main([str(CORPUS), str(tmp_path / "none.json"), "--repick", "滷肉飯"], ask=Scripted())
    assert code != 0


def test_full_run_with_an_unknown_name_exits_non_zero_before_any_call(tmp_path: Path) -> None:
    ask = Scripted()
    code, out = pick(tmp_path, ["滷肉飯", "肉夾饃"], ask)
    assert code != 0
    assert ask.prompts == []
    assert not out.exists()


def test_full_run_with_a_repeated_name_exits_non_zero(tmp_path: Path) -> None:
    code, _ = pick(tmp_path, ["滷肉飯", "滷肉飯"], Scripted())
    assert code != 0


def test_full_run_starts_a_fresh_file(tmp_path: Path) -> None:
    pick(tmp_path, ["滷肉飯", "油飯"], Scripted("[]", "[]"))
    code, out = pick(tmp_path, ["油飯"], Scripted('["滷肉飯"]'))
    assert code == 0
    records = load_distractors(out)
    assert list(records) == ["油飯"]
    assert [r.round for r in records["油飯"].rounds] == [1]


def test_prompt_without_a_placeholder_exits_non_zero_before_any_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("no placeholders: {target}", encoding="utf-8")
    monkeypatch.setattr(distractors, "PROMPT_PATH", prompt)
    ask = Scripted()
    code, _ = pick(tmp_path, ["滷肉飯"], ask)
    assert code != 0
    assert ask.prompts == []


# file content, a word of the one problem line
BAD_FILES = [
    ("{", "not valid JSON"),
    ("[]", "JSON object keyed by official name"),
    (
        '{"滷肉飯": {"rounds": [{"round": 1, "kept": [], "dropped": [], "invalid_reply": null}]}}',
        "'current' is a required property",
    ),
    ('{"滷肉飯": {"rounds": [], "current": []}}', "滷肉飯/rounds"),
    (
        '{"滷肉飯": {"rounds": [{"round": 2, "kept": [], "dropped": [], "invalid_reply": null}],'
        ' "current": []}}',
        "numbered [2]",
    ),
    (
        '{"滷肉飯": {"rounds": [{"round": 1, "kept": [], "dropped": [{"pick": "x"}],'
        ' "invalid_reply": null}], "current": []}}',
        "'reason' is a required property",
    ),
    (
        '{"滷肉飯": {"rounds": [{"round": 1, "kept": [], "dropped": [], "invalid_reply": null}],'
        ' "current": "焢肉飯"}}',
        "滷肉飯/current",
    ),
]


@pytest.mark.parametrize(("content", "reason"), BAD_FILES)
def test_loader_rejects_a_malformed_file(tmp_path: Path, content: str, reason: str) -> None:
    path = tmp_path / "distractors.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DistractorFileError) as raised:
        load_distractors(path)
    assert len(raised.value.problems) == 1
    assert reason in raised.value.problems[0]
