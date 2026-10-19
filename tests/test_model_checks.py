"""Model checks: the structured-output check with scripted replies, and the real request's
settings."""

import json
from typing import Any

import pytest
from langchain_ollama import ChatOllama

from dont_say_oyster import model_checks
from dont_say_oyster.model_checks import (
    CHALLENGER,
    DESCRIBER,
    GUESSER,
    MODELS,
    TEMPERATURE,
    ModelError,
    Reply,
    Request,
    base_url,
    chat_model,
    main,
    parse_reply,
)

GOOD = {
    "describer": {"text": "A chewy drink with tapioca balls."},
    "challenger": {"verdict": "fail", "reason": "It also fits another drink."},
    "guesser": {"kind": "guess", "text": "珍珠奶茶", "confidence": 0.8},
}


class Scripted:
    """A stand-in for the model: answers each request from `reply_for` and keeps the
    requests."""

    def __init__(self, reply_for: Any = None) -> None:
        self.reply_for = reply_for or (lambda request: good(request))
        self.requests: list[Request] = []

    def __call__(self, request: Request) -> Reply:
        self.requests.append(request)
        reply: Reply = self.reply_for(request)
        return reply


def role_of(request: Request) -> str:
    return next(m.role for m in MODELS if m.tag == request.tag)


def good(request: Request, prompt_tokens: int | None = 40) -> Reply:
    return Reply(json.dumps(GOOD[role_of(request)], ensure_ascii=False), prompt_tokens)


def run(ask: Scripted, *args: str) -> int:
    return main(["structured", *args], ask=ask)


def test_the_three_models_are_the_t1_tags_at_their_num_ctx() -> None:
    assert [(m.role, m.tag, m.num_ctx) for m in MODELS] == [
        ("describer", "qwen3.8:27b-q4_K_M", 8192),
        ("challenger", "gemma4:12b-it-q4_K_M", 4096),
        ("guesser", "gemma4:26b-a4b-it-q4_K_M", 16384),
    ]
    assert TEMPERATURE == 0.7


def test_thinking_off_is_false_and_on_is_true_or_the_qwen_default_level() -> None:
    assert [(m.think_off, m.think_on) for m in MODELS] == [
        (False, "medium"),
        (False, True),
        (False, True),
    ]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.role)
def test_a_reply_that_fits_the_role_schema_parses(model: model_checks.Model) -> None:
    assert parse_reply(model, json.dumps(GOOD[model.role])) == GOOD[model.role]


@pytest.mark.parametrize(
    ("model", "reply"),
    [
        (DESCRIBER, "A chewy drink."),
        (DESCRIBER, '{"text": "A chewy drink."'),
        (DESCRIBER, '{"description": "A chewy drink."}'),
        (DESCRIBER, '{"text": "A chewy drink.", "extra": 1}'),
        (CHALLENGER, '{"verdict": "maybe"}'),
        (CHALLENGER, '{"reason": "no verdict"}'),
        (GUESSER, '{"kind": "guess", "text": "珍珠奶茶"}'),
        (GUESSER, '{"kind": "answer", "text": "珍珠奶茶", "confidence": 0.5}'),
        (GUESSER, '{"kind": "guess", "text": "珍珠奶茶", "confidence": 1.5}'),
        (GUESSER, '["guess", "珍珠奶茶", 0.5]'),
    ],
)
def test_a_reply_that_does_not_fit_the_schema_does_not_parse(
    model: model_checks.Model, reply: str
) -> None:
    assert parse_reply(model, reply) is None


def test_a_challenger_fail_without_a_reason_parses() -> None:
    assert parse_reply(CHALLENGER, '{"verdict": "fail"}') == {"verdict": "fail"}


def test_a_reason_given_with_a_pass_is_dropped() -> None:
    reply = '{"verdict": "pass", "reason": "Fits well."}'
    assert parse_reply(CHALLENGER, reply) == {"verdict": "pass"}


def test_every_model_runs_repeat_times_with_thinking_off_then_on() -> None:
    ask = Scripted()
    assert run(ask, "--repeat", "3") == 0
    checks = ask.requests[:-2]
    expected = [
        (m.tag, m.num_ctx, think, m.schema)
        for m in MODELS
        for think in (m.think_off, m.think_on)
        for _ in range(3)
    ]
    assert [(r.tag, r.num_ctx, r.think, r.schema) for r in checks] == expected
    for r in checks:
        assert r.prompt == next(m.prompt for m in MODELS if m.tag == r.tag)


def test_repeat_defaults_to_five() -> None:
    ask = Scripted()
    assert run(ask) == 0
    assert len(ask.requests) == 3 * 2 * 5 + 2


def test_repeat_below_one_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run(Scripted(), "--repeat", "0")
    assert exit_info.value.code != 0
    assert "--repeat" in capsys.readouterr().err


def test_the_count_line_says_how_many_replies_parsed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = {"n": 0}

    def reply_for(request: Request) -> Reply:
        if request.tag == DESCRIBER.tag and request.think is False:
            calls["n"] += 1
            if calls["n"] == 2:
                return Reply("not json", 40)
        return good(request)

    assert run(Scripted(reply_for), "--repeat", "3") == 0
    out = capsys.readouterr().out
    assert f"describer {DESCRIBER.tag} think=False: 2/3 parsed" in out
    assert f"describer {DESCRIBER.tag} think=medium: 3/3 parsed" in out
    assert f"challenger {CHALLENGER.tag} think=True: 3/3 parsed" in out


def test_one_parsed_object_is_printed_per_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(Scripted(), "--repeat", "2") == 0
    out = capsys.readouterr().out
    shown = json.dumps(GOOD["guesser"], ensure_ascii=False)
    assert out.count(f"parsed object: {shown}") == 2


def test_the_raw_text_of_a_reply_that_did_not_parse_is_printed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reply_for(request: Request) -> Reply:
        if request.tag == GUESSER.tag and request.think is True:
            return Reply('{"kind": "guess",\n "text": "oops"}', 40)
        return good(request)

    run(Scripted(reply_for), "--repeat", "2")
    out = capsys.readouterr().out
    assert out.count('not parsed, raw reply: {"kind": "guess",\n "text": "oops"}') == 2


def test_each_call_prints_its_latency(capsys: pytest.CaptureFixture[str]) -> None:
    run(Scripted(), "--repeat", "2")
    out = capsys.readouterr().out
    assert out.count("call 1: ") == 6
    assert out.count("call 2: ") == 6
    assert " s, parsed" in out


def test_exit_is_non_zero_when_some_check_has_no_parsed_reply(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reply_for(request: Request) -> Reply:
        if request.tag == CHALLENGER.tag and request.think is False:
            return Reply('{"verdict": "unsure"}', 40)
        return good(request)

    assert run(Scripted(reply_for), "--repeat", "2") == 1
    out = capsys.readouterr().out
    assert f"challenger {CHALLENGER.tag} think=False: 0/2 parsed" in out
    assert "no parsed reply" in out


def test_the_same_prompt_goes_twice_to_the_guesser_and_both_token_counts_are_printed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    counts = iter([212, 3])

    def reply_for(request: Request) -> Reply:
        if request.prompt == model_checks.TOKEN_PROMPT:
            return good(request, prompt_tokens=next(counts))
        return good(request)

    ask = Scripted(reply_for)
    assert run(ask, "--repeat", "1") == 0
    first, second = ask.requests[-2:]
    assert first == second
    assert (first.tag, first.num_ctx, first.prompt) == (
        GUESSER.tag,
        GUESSER.num_ctx,
        model_checks.TOKEN_PROMPT,
    )
    assert first.prompt not in {m.prompt for m in MODELS}
    out = capsys.readouterr().out
    assert f"prompt tokens, same prompt twice to {GUESSER.tag}: 212, 3" in out


def test_a_missing_token_count_is_printed_as_none(capsys: pytest.CaptureFixture[str]) -> None:
    def reply_for(request: Request) -> Reply:
        return good(request, prompt_tokens=None)

    run(Scripted(reply_for), "--repeat", "1")
    out = capsys.readouterr().out
    assert f"prompt tokens, same prompt twice to {GUESSER.tag}: None, None" in out


def test_a_failed_model_call_stops_the_command_with_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reply_for(request: Request) -> Reply:
        raise ModelError("model call failed: ConnectionError: refused")

    assert run(Scripted(reply_for)) == 1
    assert "model call failed: ConnectionError: refused" in capsys.readouterr().err


def test_the_endpoint_comes_from_ollama_base_url_or_the_local_default() -> None:
    assert base_url({"OLLAMA_BASE_URL": "http://studio.local:11434"}) == (
        "http://studio.local:11434"
    )
    assert base_url({}) == "http://localhost:11434"
    assert base_url({"OLLAMA_BASE_URL": ""}) == "http://localhost:11434"


@pytest.mark.parametrize("think", [False, True, "medium"])
def test_the_real_request_sends_the_schema_as_format_with_the_settings(
    think: bool | str,
) -> None:
    request = Request(GUESSER.tag, GUESSER.num_ctx, think, GUESSER.schema, "prompt")
    structured = chat_model(request, "http://studio.local:11434")
    raw: Any = structured.first.steps__["raw"]  # type: ignore[attr-defined]
    llm = raw.bound
    assert isinstance(llm, ChatOllama)
    assert (llm.model, llm.num_ctx, llm.temperature, llm.reasoning, llm.base_url) == (
        GUESSER.tag,
        GUESSER.num_ctx,
        TEMPERATURE,
        think,
        "http://studio.local:11434",
    )
    assert raw.kwargs["format"] == GUESSER.schema
    assert raw.kwargs["ls_structured_output_format"]["kwargs"] == {"method": "json_schema"}
    params = llm._chat_params([], format=raw.kwargs["format"])
    assert params["think"] is think
    assert params["format"] == GUESSER.schema
    assert params["options"]["num_ctx"] == GUESSER.num_ctx
    assert params["options"]["temperature"] == TEMPERATURE


def test_no_prompt_asks_for_json() -> None:
    for prompt in [m.prompt for m in MODELS] + [model_checks.TOKEN_PROMPT]:
        assert "json" not in prompt.lower()
