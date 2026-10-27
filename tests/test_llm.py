"""The model-call wrapper with a scripted chat model: what each call returns, the run metadata
each request carries for the trace, the num_ctx warning, the client's settings, and the
errors [R26]."""

import json
import logging
import time
from collections.abc import Iterator, Sequence
from typing import Any

import httpx
import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from langchain_ollama import ChatOllama

from dont_say_oyster import llm
from dont_say_oyster.llm import LLMError, ModelSettings, call_structured, call_text, call_tools

SETTINGS = ModelSettings(
    role="guesser",
    model="gemma4:26b-a4b-it-q4_K_M",
    num_ctx=16384,
    temperature=0.7,
    thinking=False,
    keep_alive="30m",
)
MESSAGES = [HumanMessage("Guess the snack.")]
SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["guess", "confidence"],
    "additionalProperties": False,
    "properties": {
        "guess": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search the corpus.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        },
    },
}
DELAY = 0.05


def reply(
    content: str = "", input_tokens: int = 120, output_tokens: int = 30, **kw: Any
) -> AIMessage:
    return AIMessage(
        content=content,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        **kw,
    )


class Scripted(GenericFakeChatModel):
    """A fake chat model that answers from `messages` after `delay` seconds and keeps the
    keyword arguments and the run metadata of each request it receives."""

    requests: list[dict[str, Any]] = []
    run_metadata: list[dict[str, Any]] = []
    delay: float = 0.0

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.requests.append(kwargs)
        self.run_metadata.append(dict(run_manager.metadata) if run_manager else {})
        time.sleep(self.delay)
        return super()._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(
        self, tools: Sequence[Any], **kwargs: Any
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self.bind(tools=list(tools), **kwargs)


def scripted(*replies: AIMessage, delay: float = 0.0) -> Scripted:
    return Scripted(messages=iter(replies), requests=[], delay=delay)


def raising(error: Exception) -> Scripted:
    def messages() -> Iterator[AIMessage]:
        raise error
        yield  # pragma: no cover

    return Scripted(messages=messages(), requests=[])


class Clients:
    """A client factory that hands out `model` and keeps the settings it was asked for."""

    def __init__(self, model: Scripted) -> None:
        self.model = model
        self.settings: list[ModelSettings] = []

    def __call__(self, settings: ModelSettings) -> Scripted:
        self.settings.append(settings)
        return self.model


def test_a_plain_call_returns_the_text_with_latency_tokens_and_attempt() -> None:
    clients = Clients(scripted(reply("A chewy drink.", 120, 30), delay=DELAY))
    result = call_text(SETTINGS, MESSAGES, attempt=3, client_for=clients)
    assert result.output == "A chewy drink."
    assert (result.input_tokens, result.output_tokens, result.attempt) == (120, 30, 3)
    assert result.latency >= DELAY
    assert clients.settings == [SETTINGS]
    assert clients.model.requests == [{}]


def test_a_structured_call_returns_the_parsed_object_with_latency_tokens_and_attempt() -> None:
    answer = {"guess": "珍珠奶茶", "confidence": 0.8}
    clients = Clients(scripted(reply(json.dumps(answer), 200, 12), delay=DELAY))
    result = call_structured(SETTINGS, MESSAGES, SCHEMA, attempt=3, client_for=clients)
    assert result.output == answer
    assert (result.input_tokens, result.output_tokens, result.attempt) == (200, 12, 3)
    assert result.latency >= DELAY
    assert clients.model.requests == [{"format": SCHEMA}]


def test_a_tool_bound_call_returns_the_message_with_latency_tokens_and_attempt() -> None:
    call = {"name": "search", "args": {"keywords": ["boba"]}, "id": "c1", "type": "tool_call"}
    clients = Clients(scripted(reply("", 300, 20, tool_calls=[call]), delay=DELAY))
    result = call_tools(SETTINGS, MESSAGES, [TOOL], attempt=3, client_for=clients)
    assert isinstance(result.output, AIMessage)
    assert result.output.tool_calls == [call]
    assert (result.input_tokens, result.output_tokens, result.attempt) == (300, 20, 3)
    assert result.latency >= DELAY
    assert clients.model.requests == [{"tools": [TOOL]}]


def ours(run_metadata: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The run metadata without the keys LangChain adds itself (`ls_*`, `lc_versions`)."""
    return [
        {k: v for k, v in m.items() if not k.startswith(("ls_", "lc_"))} for m in run_metadata
    ]


def test_each_call_carries_the_role_the_attempt_and_its_kind_in_its_run_metadata() -> None:
    call = {"name": "search", "args": {"keywords": ["boba"]}, "id": "c1", "type": "tool_call"}
    model = scripted(
        reply("A chewy drink."),
        reply(json.dumps({"guess": "珍珠奶茶", "confidence": 0.8})),
        reply("", tool_calls=[call]),
    )
    clients = Clients(model)
    call_text(SETTINGS, MESSAGES, attempt=1, client_for=clients)
    call_structured(SETTINGS, MESSAGES, SCHEMA, attempt=2, client_for=clients)
    call_tools(SETTINGS, MESSAGES, [TOOL], attempt=3, client_for=clients)
    assert ours(model.run_metadata) == [
        {"role": "guesser", "attempt": 1, "kind": "text"},
        {"role": "guesser", "attempt": 2, "kind": "structured"},
        {"role": "guesser", "attempt": 3, "kind": "tools"},
    ]


def test_the_callers_metadata_is_merged_and_cannot_override_role_attempt_or_kind() -> None:
    model = scripted(reply(""), reply("x"), reply(json.dumps({"guess": "x", "confidence": 1})))
    clients = Clients(model)
    call_tools(
        SETTINGS, MESSAGES, [TOOL], attempt=1, client_for=clients,
        metadata={"round": 2, "call": 3},
    )
    call_text(SETTINGS, MESSAGES, attempt=1, client_for=clients, metadata={"attempt": 9})
    call_structured(
        SETTINGS, MESSAGES, SCHEMA, attempt=1, client_for=clients, metadata={"kind": "tools"}
    )
    assert ours(model.run_metadata) == [
        {"round": 2, "call": 3, "role": "guesser", "attempt": 1, "kind": "tools"},
        {"role": "guesser", "attempt": 1, "kind": "text"},
        {"role": "guesser", "attempt": 1, "kind": "structured"},
    ]
    assert model.requests[0] == {"tools": [TOOL]}  # the metadata is not a request argument


def test_prompt_tokens_over_90_percent_of_num_ctx_log_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = ModelSettings("describer", "qwen3.8:27b-q4_K_M", 1000, 0.7, False, "30m")
    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        call_text(settings, MESSAGES, attempt=1, client_for=Clients(scripted(reply("x", 901))))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].name == llm.__name__
    message = warnings[0].getMessage()
    assert "describer" in message and "901" in message and "1000" in message


def test_prompt_tokens_at_90_percent_of_num_ctx_log_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = ModelSettings("describer", "qwen3.8:27b-q4_K_M", 1000, 0.7, False, "30m")
    with caplog.at_level(logging.DEBUG, logger=llm.__name__):
        call_text(settings, MESSAGES, attempt=1, client_for=Clients(scripted(reply("x", 900))))
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_a_reply_without_token_counts_logs_one_warning_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = ModelSettings("describer", "qwen3.8:27b-q4_K_M", 1000, 0.7, False, "30m")
    model = scripted(AIMessage(content="x"))
    with caplog.at_level(logging.DEBUG, logger=llm.__name__):
        result = call_text(settings, MESSAGES, attempt=1, client_for=Clients(model))
    assert (result.input_tokens, result.output_tokens) == (None, None)
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [(r.name, r.getMessage()) for r in warnings] == [
        (llm.__name__, "describer: Ollama reported no token counts")
    ]


def test_a_reply_with_token_counts_under_90_percent_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger=llm.__name__):
        call_text(SETTINGS, MESSAGES, attempt=1, client_for=Clients(scripted(reply("x"))))
    assert [r for r in caplog.records if r.name == llm.__name__] == []


@pytest.mark.parametrize(
    ("thinking", "keep_alive"), [(False, 0), (True, "30m"), ("medium", 1800)]
)
def test_the_client_is_built_with_the_settings_passed_in(
    thinking: bool | str, keep_alive: int | str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://studio.local:11434")
    settings = ModelSettings("challenger", "gemma4:12b-it-q4_K_M", 4096, 0.7, thinking, keep_alive)
    client = llm.ollama_client(settings)
    assert isinstance(client, ChatOllama)
    assert (
        client.model,
        client.num_ctx,
        client.temperature,
        client.reasoning,
        client.keep_alive,
        client.base_url,
    ) == ("gemma4:12b-it-q4_K_M", 4096, 0.7, thinking, keep_alive, "http://studio.local:11434")
    params = client._chat_params([])
    assert params["keep_alive"] == keep_alive
    assert params["think"] == thinking
    assert params["options"]["num_ctx"] == 4096
    assert params["options"]["temperature"] == 0.7


def test_the_endpoint_falls_back_to_the_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "load_dotenv", lambda: False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert llm.ollama_client(SETTINGS).base_url == "http://localhost:11434"


@pytest.mark.parametrize(
    "text", ["not json", json.dumps({"guess": "珍珠奶茶", "confidence": 2})], ids=["text", "schema"]
)
def test_a_structured_reply_that_does_not_parse_raises_after_one_request(text: str) -> None:
    model = scripted(reply(text), reply(json.dumps({"guess": "珍珠奶茶", "confidence": 0.5})))
    with pytest.raises(LLMError, match="guesser"):
        call_structured(SETTINGS, MESSAGES, SCHEMA, attempt=1, client_for=Clients(model))
    assert len(model.requests) == 1


@pytest.mark.parametrize(
    "error",
    [ConnectionError("Failed to connect to Ollama"), httpx.ConnectError("refused")],
    ids=["ollama", "httpx"],
)
@pytest.mark.parametrize("kind", ["text", "structured", "tools"])
def test_a_connection_error_raises_after_one_request(error: Exception, kind: str) -> None:
    model = raising(error)
    clients = Clients(model)
    with pytest.raises(LLMError, match="guesser") as raised:
        if kind == "text":
            call_text(SETTINGS, MESSAGES, attempt=1, client_for=clients)
        elif kind == "structured":
            call_structured(SETTINGS, MESSAGES, SCHEMA, attempt=1, client_for=clients)
        else:
            call_tools(SETTINGS, MESSAGES, [TOOL], attempt=1, client_for=clients)
    assert raised.value.__cause__ is error
    assert len(model.requests) == 1


@pytest.mark.parametrize(
    "error",
    [
        OutputParserException("Function search arguments are not valid JSON"),
        ValueError("No data received from Ollama stream."),
        json.JSONDecodeError("Expecting value", "not json", 0),
    ],
    ids=["output-parser", "empty-stream", "bad-line"],
)
@pytest.mark.parametrize("kind", ["text", "structured", "tools"])
def test_a_reply_the_client_cannot_read_raises_after_one_request(
    error: Exception, kind: str
) -> None:
    model = raising(error)
    clients = Clients(model)
    with pytest.raises(LLMError, match="guesser: reply did not parse") as raised:
        if kind == "text":
            call_text(SETTINGS, MESSAGES, attempt=1, client_for=clients)
        elif kind == "structured":
            call_structured(SETTINGS, MESSAGES, SCHEMA, attempt=1, client_for=clients)
        else:
            call_tools(SETTINGS, MESSAGES, [TOOL], attempt=1, client_for=clients)
    assert raised.value.__cause__ is error
    assert len(model.requests) == 1


DONE = {
    "model": "m",
    "created_at": "2026-10-19T00:00:00Z",
    "done": True,
    "done_reason": "stop",
    "prompt_eval_count": 5,
    "eval_count": 1,
}
STRING_ARGUMENTS = {
    **DONE,
    "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "search", "arguments": "{bad"}}],
    },
}


@pytest.mark.parametrize(
    "body",
    [b"not json\n", b"", (json.dumps(STRING_ARGUMENTS) + "\n").encode()],
    ids=["bad-line", "empty-stream", "string-arguments"],
)
def test_a_bad_stream_through_chatollama_raises_after_one_http_request(body: bytes) -> None:
    sent: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=body)

    def client_for(settings: ModelSettings) -> ChatOllama:
        return ChatOllama(
            model=settings.model, client_kwargs={"transport": httpx.MockTransport(respond)}
        )

    with pytest.raises(LLMError, match="guesser: reply did not parse") as raised:
        call_tools(SETTINGS, MESSAGES, [TOOL], attempt=1, client_for=client_for)
    assert isinstance(raised.value.__cause__, ValueError)
    assert len(sent) == 1
