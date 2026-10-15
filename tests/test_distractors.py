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
    ModelError,
    Pick,
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


def answer(*names: str) -> str:
    """A well-formed reply naming `names` in order; each why says which place it held."""
    picks = [{"name": n, "why": f"why {i}"} for i, n in enumerate(names)]
    return json.dumps(picks, ensure_ascii=False)


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
    reply = answer(
        *("滷肉飯", "肉夾饃", "焢肉飯", "焢肉飯", "腿庫飯"),
        *("火雞肉飯", "鴨肉飯", "鵝肉飯", "燻鵝", "鹽水鵝"),
    )
    code, out = pick(tmp_path, ["滷肉飯"], Scripted(reply))
    assert code == 0
    record = load_distractors(out)["滷肉飯"]
    assert record.current == ("焢肉飯", "腿庫飯", "火雞肉飯", "鴨肉飯", "鵝肉飯")
    (only,) = record.rounds
    assert only.round == 1
    assert only.kept == (
        Pick("焢肉飯", "why 2"),
        Pick("腿庫飯", "why 4"),
        Pick("火雞肉飯", "why 5"),
        Pick("鴨肉飯", "why 6"),
        Pick("鵝肉飯", "why 7"),
    )
    assert only.dropped == (
        DroppedPick("滷肉飯", "why 0", "the card itself"),
        DroppedPick("肉夾饃", "why 1", "not a name in the corpus"),
        DroppedPick("焢肉飯", "why 3", "repeats an earlier pick"),
        DroppedPick("燻鵝", "why 8", "over the limit of 5"),
        DroppedPick("鹽水鵝", "why 9", "over the limit of 5"),
    )
    assert only.invalid_reply is None


def test_alias_pick_is_dropped_naming_its_entry(tmp_path: Path) -> None:
    code, out = pick(tmp_path, ["油飯"], Scripted(answer("魯肉飯", "筒仔米糕")))
    assert code == 0
    (only,) = load_distractors(out)["油飯"].rounds
    assert only.kept == (Pick("筒仔米糕", "why 1"),)
    assert only.dropped == (
        DroppedPick("魯肉飯", "why 0", "an alias of 滷肉飯, not an official name"),
    )


def test_empty_reply_gives_an_empty_current_list(tmp_path: Path) -> None:
    code, out = pick(tmp_path, ["滷肉飯"], Scripted("[]"))
    assert code == 0
    record = load_distractors(out)["滷肉飯"]
    assert record.current == ()
    assert record.rounds[0].kept == ()
    assert record.rounds[0].dropped == ()
    assert record.rounds[0].invalid_reply is None


NOT_PICKS = [
    "Here are the picks: 焢肉飯",
    "",
    '{"name": "焢肉飯", "why": "w"}',  # an object, not an array
    '["焢肉飯"]',  # names without objects, the old format
    '[{"name": "焢肉飯", "why": "w"}, "腿庫飯"]',
    '[{"name": "焢肉飯"}]',  # no why
    '[{"why": "w"}]',  # no name
    '[{"name": "焢肉飯", "why": "w", "rank": 1}]',  # an extra key
    '[{"name": "焢肉飯", "why": 3}]',
    '[{"name": ["焢肉飯"], "why": "w"}]',
]


@pytest.mark.parametrize("reply", NOT_PICKS)
def test_reply_that_is_not_an_array_of_name_why_objects_is_zero_picks_and_the_run_continues(
    tmp_path: Path, reply: str
) -> None:
    code, out = pick(tmp_path, ["滷肉飯", "油飯"], Scripted(reply, answer("筒仔米糕")))
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
    ask = Scripted(answer("焢肉飯", "腿庫飯"), answer("筒仔米糕"), answer("油飯", "鴨肉飯"))
    code, out = pick(tmp_path, ["滷肉飯", "油飯", "筒仔米糕"], ask)
    assert code == 0

    # The author edits one name's current list by hand.
    data = json.loads(out.read_text(encoding="utf-8"))
    data["油飯"]["current"] = ["筒仔米糕", "滷肉飯"]
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    before = load_distractors(out)

    code = main([str(CORPUS), str(out), "--repick", "筒仔米糕"], ask=Scripted(answer("鵝肉飯")))
    assert code == 0
    after = load_distractors(out)

    assert list(after) == ["滷肉飯", "油飯", "筒仔米糕"]
    assert after["滷肉飯"] == before["滷肉飯"]
    assert after["油飯"] == before["油飯"]
    assert after["油飯"].current == ("筒仔米糕", "滷肉飯")
    repicked = after["筒仔米糕"]
    assert [r.round for r in repicked.rounds] == [1, 2]
    assert repicked.rounds[0] == before["筒仔米糕"].rounds[0]
    assert repicked.rounds[1].kept == (Pick("鵝肉飯", "why 0"),)
    assert repicked.current == ("鵝肉飯",)


def test_repick_of_a_name_not_in_the_corpus_exits_non_zero_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = pick(tmp_path, ["滷肉飯"], Scripted(answer("焢肉飯")))
    assert code == 0
    before = out.read_bytes()
    ask = Scripted()
    code = main([str(CORPUS), str(out), "--repick", "滷肉飯", "肉夾饃"], ask=ask)
    assert code != 0
    assert "肉夾饃" in capsys.readouterr().err
    assert ask.prompts == []
    assert out.read_bytes() == before


def test_repick_of_a_corpus_name_not_yet_in_the_file_adds_it_with_round_1(
    tmp_path: Path,
) -> None:
    code, out = pick(tmp_path, ["滷肉飯"], Scripted(answer("焢肉飯")))
    assert code == 0
    before = load_distractors(out)
    code = main([str(CORPUS), str(out), "--repick", "鵝肉飯"], ask=Scripted(answer("燻鵝")))
    assert code == 0
    after = load_distractors(out)
    assert list(after) == ["滷肉飯", "鵝肉飯"]
    assert after["滷肉飯"] == before["滷肉飯"]
    assert [r.round for r in after["鵝肉飯"].rounds] == [1]
    assert after["鵝肉飯"].current == ("燻鵝",)


def test_model_error_prints_one_line_exits_non_zero_and_keeps_the_names_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailsAfterFirstCall(Scripted):
        def __call__(self, prompt: str) -> str:
            if self.prompts:
                raise ModelError("model call failed: APIConnectionError: Connection error.")
            return super().__call__(prompt)

    ask = FailsAfterFirstCall(answer("焢肉飯"))
    out = tmp_path / "distractors.json"
    names = names_file(tmp_path, ["滷肉飯", "油飯", "筒仔米糕"])
    code = main([str(CORPUS), str(out), "--names", str(names)], ask=ask)
    assert code != 0
    err = capsys.readouterr().err.strip().splitlines()
    assert err[-1] == "油飯: model call failed: APIConnectionError: Connection error."
    assert "Traceback" not in "\n".join(err)
    assert list(load_distractors(out)) == ["滷肉飯"]


def test_model_ask_turns_an_api_error_into_a_model_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic
    import httpx2

    class Failing:
        def invoke(self, prompt: str) -> None:
            request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.APIConnectionError(message="Connection\nerror.", request=request)

    monkeypatch.setattr(distractors, "model_client", Failing)
    with pytest.raises(ModelError) as raised:
        distractors.model_ask()("prompt")
    assert str(raised.value) == "model call failed: APIConnectionError: Connection error."


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
    code, out = pick(tmp_path, ["油飯"], Scripted(answer("滷肉飯")))
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
        '{"滷肉飯": {"rounds": [{"round": 1, "kept": [], "dropped": [{"name": "x", "reason": "r"}],'
        ' "invalid_reply": null}], "current": []}}',
        "'why' is a required property",
    ),
    (
        '{"滷肉飯": {"rounds": [{"round": 1, "kept": ["焢肉飯"], "dropped": [],'
        ' "invalid_reply": null}], "current": ["焢肉飯"]}}',
        "滷肉飯/rounds/0/kept/0",
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


def test_model_client_asks_for_adaptive_thinking_at_effort_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    payload = distractors.model_client()._get_request_payload("hello")
    assert payload["model"] == "claude-opus-5-5"
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["output_config"] == {"effort": "high"}
