"""Model checks: the structured-output and tool-calling checks with scripted replies, and the
real requests' settings."""

import json
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_ollama import ChatOllama

from dont_say_oyster import model_checks
from dont_say_oyster.corpus import SCHEMA_PATH
from dont_say_oyster.model_checks import (
    CHALLENGER,
    DESCRIBER,
    GUESS_SCHEMA,
    GUESSER,
    MODELS,
    SEARCH_RESULT,
    SEARCH_TOOL,
    TEMPERATURE,
    ChatReply,
    ChatRequest,
    ModelError,
    Reply,
    Request,
    base_url,
    chat_model,
    enum_check,
    main,
    model_chat,
    parse_guess,
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


# The tools subcommand [R44], [R47], [R48].

LISTED = {
    field: json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["items"]["properties"]["attributes"][
        "properties"
    ][field]["items"]["enum"]
    for field in ("main_ingredients", "cooking_method", "physical_form")
}
FILTERS = {
    "main_ingredients": ["Sugar and Sweeteners", "Milk"],
    "physical_form": ["Drink with Add-ins"],
}
GOOD_GUESS = {"guess": "黑糖珍珠鮮奶", "confidence": 0.8}


def tool_reply(*arguments: dict[str, Any], text: str = "") -> ChatReply:
    calls = [{"name": "search", "args": a, "id": f"call_{n}"} for n, a in enumerate(arguments)]
    return ChatReply(AIMessage(text, tool_calls=calls), arguments)


def guess_reply(text: str = json.dumps(GOOD_GUESS, ensure_ascii=False)) -> ChatReply:
    return ChatReply(AIMessage(text), ())


class ScriptedChat:
    """A stand-in for the Guesser's model: answers a request with tools from `tool` and one
    with a schema from `guess`, and keeps the requests."""

    def __init__(self, tool: Any = None, guess: Any = None) -> None:
        self.tool = tool or (lambda request: tool_reply(FILTERS))
        self.guess = guess or (lambda request: guess_reply())
        self.requests: list[ChatRequest] = []

    def __call__(self, request: ChatRequest) -> ChatReply:
        self.requests.append(request)
        reply: ChatReply = self.guess(request) if request.schema is not None else self.tool(request)
        return reply


def run_tools(chat: ScriptedChat, *args: str) -> int:
    return main(["tools", *args], chat=chat)


def test_the_search_tool_has_optional_enum_filters_from_the_schema_and_keywords() -> None:
    function = SEARCH_TOOL["function"]
    parameters = function["parameters"]
    assert function["name"] == "search"
    assert parameters["required"] == []
    assert set(parameters["properties"]) == {*LISTED, "keywords"}
    for field, values in LISTED.items():
        prop = parameters["properties"][field]
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "string", "enum": values}
    assert "Sugar and Sweeteners" in LISTED["main_ingredients"]
    assert parameters["properties"]["keywords"]["items"] == {"type": "string"}


def test_the_stand_in_returns_two_entries_with_the_r45_fields() -> None:
    entries = json.loads(SEARCH_RESULT)
    assert len(entries) == 2
    for entry in entries:
        assert set(entry) == {"official_name", "aliases", "english_names", "attributes"}


def test_the_guess_schema_is_a_guess_and_a_confidence() -> None:
    assert GUESS_SCHEMA["required"] == ["guess", "confidence"]
    assert parse_guess('{"guess": "珍珠奶茶", "confidence": 0.5}') == {
        "guess": "珍珠奶茶",
        "confidence": 0.5,
    }
    assert parse_guess('{"guess": "珍珠奶茶", "confidence": 1.5}') is None
    assert parse_guess('{"guess": "珍珠奶茶"}') is None
    assert parse_guess("珍珠奶茶") is None


def test_each_run_calls_with_the_tool_then_the_guess_call_with_no_tool() -> None:
    chat = ScriptedChat()
    assert run_tools(chat, "--repeat", "2") == 0
    assert len(chat.requests) == 2 * 2 * 2
    thinks = [r.think for r in chat.requests]
    assert thinks == [GUESSER.think_off] * 4 + [GUESSER.think_on] * 4
    for r in chat.requests:
        assert (r.tag, r.num_ctx) == (GUESSER.tag, GUESSER.num_ctx)
    for tool_call, guess_call in zip(chat.requests[::2], chat.requests[1::2], strict=True):
        assert tool_call.tools == (SEARCH_TOOL,)
        assert tool_call.schema is None
        assert [m.content for m in tool_call.messages] == [model_checks.TOOL_PROMPT]
        assert guess_call.tools == ()
        assert guess_call.schema == GUESS_SCHEMA


def test_a_scripted_tool_call_is_run_and_its_result_sent_back() -> None:
    chat = ScriptedChat()
    run_tools(chat, "--repeat", "1")
    reply = tool_reply(FILTERS)
    human, ai, tool = chat.requests[1].messages
    assert isinstance(human, HumanMessage)
    assert isinstance(ai, AIMessage)
    assert ai.tool_calls == reply.message.tool_calls
    assert isinstance(tool, ToolMessage)
    assert (tool.content, tool.tool_call_id) == (SEARCH_RESULT, "call_0")


def test_each_tool_call_in_one_reply_gets_its_own_result_in_order() -> None:
    chat = ScriptedChat(tool=lambda request: tool_reply(FILTERS, {"keywords": ["boba"]}))
    run_tools(chat, "--repeat", "1")
    results = chat.requests[1].messages[2:]
    assert [(m.content, m.tool_call_id) for m in results] == [  # type: ignore[attr-defined]
        (SEARCH_RESULT, "call_0"),
        (SEARCH_RESULT, "call_1"),
    ]


def test_the_arguments_are_printed_as_the_model_sent_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = {"main_ingredients": ["Sugar and Sweeteners"], "keywords": '["boba"]'}
    message = AIMessage(
        "",
        tool_calls=[{"name": "search", "args": {**sent, "keywords": ["boba"]}, "id": "call_0"}],
    )
    chat = ScriptedChat(tool=lambda request: ChatReply(message, (sent,)))
    run_tools(chat, "--repeat", "1")
    out = capsys.readouterr().out
    assert f"search {json.dumps(sent, ensure_ascii=False)}" in out
    assert (
        'LangChain args: {"main_ingredients": ["Sugar and Sweeteners"], "keywords": ["boba"]}'
        in (out)
    )


def test_each_enum_value_is_reported_listed_or_not(capsys: pytest.CaptureFixture[str]) -> None:
    sent = {
        "main_ingredients": ["Sugar and Sweeteners", "sugar and sweeteners"],
        "physical_form": "Drink with add-ins",
        "cooking_method": ["No Cooking", 3],
        "flavor": ["Sweet"],
        "keywords": ["boba"],
    }
    chat = ScriptedChat(tool=lambda request: tool_reply(sent))
    assert run_tools(chat, "--repeat", "1") == 0
    out = capsys.readouterr().out
    assert 'main_ingredients "Sugar and Sweeteners": listed' in out
    assert 'main_ingredients "sugar and sweeteners": not listed' in out
    assert 'physical_form "Drink with add-ins": not listed' in out
    assert 'cooking_method "No Cooking": listed' in out
    assert "cooking_method 3: not listed" in out
    assert "flavor: not a tool argument" in out
    assert 'keywords "boba"' not in out
    assert "4 enum values or arguments not listed" in out


def test_enum_check_marks_values_and_unknown_arguments() -> None:
    assert enum_check({"physical_form": ["Drink with Add-ins"], "keywords": ["x"]}) == [
        'physical_form "Drink with Add-ins": listed'
    ]
    assert enum_check({"main_ingredients": "Tea"}) == ['main_ingredients "Tea": listed']
    assert enum_check({"occasion": ["Night Market"]}) == ["occasion: not a tool argument"]


def test_the_count_line_says_how_many_runs_called_the_tool_and_how_many_guesses_parsed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = {"tool": 0, "guess": 0}

    def tool(request: ChatRequest) -> ChatReply:
        calls["tool"] += 1
        return tool_reply(FILTERS) if calls["tool"] != 2 else tool_reply(text="It is boba milk.")

    def guess(request: ChatRequest) -> ChatReply:
        calls["guess"] += 1
        return guess_reply() if calls["guess"] != 1 else guess_reply("not json")

    assert run_tools(ScriptedChat(tool, guess), "--repeat", "3") == 0
    out = capsys.readouterr().out
    assert (
        f"guesser {GUESSER.tag} think=False: 2/3 runs made a tool call, 2/3 guess calls "
        "parsed, 1 after a tool call" in out
    )
    assert (
        f"guesser {GUESSER.tag} think=True: 3/3 runs made a tool call, 3/3 guess calls "
        "parsed, 3 after a tool call" in out
    )


def test_a_reply_without_a_tool_call_prints_its_raw_text_and_the_guess_call_still_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chat = ScriptedChat(tool=lambda request: tool_reply(text="I think it is boba."))
    assert run_tools(chat, "--repeat", "1") == 1
    out = capsys.readouterr().out
    assert out.count("no tool call, raw reply: I think it is boba.") == 2
    assert len(chat.requests) == 4
    assert [type(m) for m in chat.requests[1].messages] == [HumanMessage, AIMessage]
    assert "no tool call followed by a parsed guess call: think=False; think=True" in out


def test_a_guess_that_does_not_parse_prints_its_raw_text_and_fails_the_setting(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def guess(request: ChatRequest) -> ChatReply:
        return guess_reply('{"guess": "x"}') if request.think is True else guess_reply()

    assert run_tools(ScriptedChat(guess=guess), "--repeat", "2") == 1
    out = capsys.readouterr().out
    assert out.count('not parsed, raw reply: {"guess": "x"}') == 2
    assert "no tool call followed by a parsed guess call: think=True" in out


def test_each_tools_call_prints_its_latency(capsys: pytest.CaptureFixture[str]) -> None:
    run_tools(ScriptedChat(), "--repeat", "2")
    out = capsys.readouterr().out
    assert out.count("run 1: tool call ") == 2
    assert out.count("guess call ") == 4


def test_tools_repeat_defaults_to_five() -> None:
    chat = ScriptedChat()
    assert run_tools(chat) == 0
    assert len(chat.requests) == 2 * 5 * 2


def test_a_failed_chat_call_stops_the_tools_command_with_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def tool(request: ChatRequest) -> ChatReply:
        raise ModelError("model call failed: ConnectionError: refused")

    assert run_tools(ScriptedChat(tool=tool)) == 1
    assert "model call failed: ConnectionError: refused" in capsys.readouterr().err


def test_the_tool_prompt_does_not_ask_for_json() -> None:
    assert "json" not in model_checks.TOOL_PROMPT.lower()


class Ollama:
    """A stand-in Ollama server behind httpx.MockTransport: keeps each /api/chat body and
    streams back NDJSON lines, `tool_lines` for a request with tools, one JSON guess for any
    other."""

    def __init__(self, tool_lines: list[dict[str, Any]]) -> None:
        self.tool_lines = tool_lines
        self.bodies: list[dict[str, Any]] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if body.get("tools"):
            lines = self.tool_lines
        else:
            text = json.dumps(GOOD_GUESS, ensure_ascii=False)
            lines = [{"model": body["model"], "message": {"role": "assistant", "content": text}}]
        lines = [
            *lines,
            {
                "model": body["model"],
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 50,
                "eval_count": 5,
            },
        ]
        chunks = [(json.dumps(line, ensure_ascii=False) + "\n").encode() for line in lines]
        return httpx.Response(200, content=iter(chunks))


def ollama_tool_call(arguments: dict[str, Any]) -> dict[str, Any]:
    call = {"function": {"name": "search", "arguments": arguments}}
    return {
        "model": GUESSER.tag,
        "message": {"role": "assistant", "content": "", "tool_calls": [call]},
    }


@pytest.mark.parametrize("think", [False, True])
def test_the_real_requests_bind_the_tool_then_send_the_guess_call_with_no_tool(
    think: bool,
) -> None:
    server = Ollama([ollama_tool_call(FILTERS)])
    chat = model_chat(server.transport)
    first = ChatRequest(
        GUESSER.tag, GUESSER.num_ctx, think, (HumanMessage("p"),), (SEARCH_TOOL,), None
    )
    reply = chat(first)
    assert reply.message.tool_calls[0]["args"] == FILTERS
    assert reply.sent_arguments == (FILTERS,)
    result = ToolMessage(SEARCH_RESULT, tool_call_id=reply.message.tool_calls[0]["id"])
    second = ChatRequest(
        GUESSER.tag,
        GUESSER.num_ctx,
        think,
        (HumanMessage("p"), reply.message, result),
        (),
        GUESS_SCHEMA,
    )
    assert parse_guess(chat(second).message.text) == GOOD_GUESS

    tool_body, guess_body = server.bodies
    for body in server.bodies:
        assert body["model"] == GUESSER.tag
        assert body["think"] is think
        assert body["options"] == {"num_ctx": GUESSER.num_ctx, "temperature": TEMPERATURE}
    sent_tool = tool_body["tools"][0]["function"]
    assert sent_tool["name"] == "search"
    for field, values in LISTED.items():
        assert sent_tool["parameters"]["properties"][field]["items"]["enum"] == values
    assert "format" not in tool_body
    assert not guess_body.get("tools")
    assert guess_body["format"] == GUESS_SCHEMA
    assert guess_body["messages"][-1] == {"role": "tool", "content": SEARCH_RESULT}
    assert guess_body["messages"][1]["tool_calls"] == [
        {"function": {"name": "search", "arguments": FILTERS}}
    ]


def test_the_real_reply_keeps_the_arguments_ollama_sent_where_langchain_rewrites_them() -> None:
    sent = {"physical_form": ["Drink with Add-ins"], "keywords": '["boba"]'}
    server = Ollama([ollama_tool_call(sent)])
    chat = model_chat(server.transport)
    reply = chat(
        ChatRequest(GUESSER.tag, GUESSER.num_ctx, False, (HumanMessage("p"),), (SEARCH_TOOL,), None)
    )
    assert reply.sent_arguments == (sent,)
    assert reply.message.tool_calls[0]["args"]["keywords"] == ["boba"]
