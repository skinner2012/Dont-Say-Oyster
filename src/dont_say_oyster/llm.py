"""The model-call wrapper every role uses [R26].

One wrapper call is one request to Ollama through langchain-ollama: a plain-text call, a
structured-output call (the JSON schema sent as Ollama's `format`, as `with_structured_output`
with method `json_schema` sends it, T2), or a call with tools bound (`bind_tools`, T3). The model,
num_ctx, temperature, thinking setting, and keep_alive are the caller's and are forwarded to
ChatOllama as given; the attempt number is the caller's too [R26] and is passed through.

Each request carries run metadata for the trace (M3 T3): the role, the attempt number, and the
kind of call (`text`, `structured`, or `tools`), passed as `config["metadata"]` to `invoke`, so
the callback handler puts them on the call's generation span; the handler sees the model tag but
not the role, and cannot know the attempt number [R26], which the caller computes. A caller may
add keys of its own (`metadata`): the Guesser's tool loop adds the round and the tool-loop call
index, which its tool spans carry too, since a tool runs after the call returns and its span is
a sibling of the generation span, not its child. The token counts and the latency on the span
need no code: the handler reads the same `usage_metadata` this wrapper reads, and the span's
duration is the latency around the same `invoke`.

Each call returns its output with the latency (wall time around the one request, thinking and
any model load included; `SPEC.md` Metrics, Latency) and the input and output token counts
Ollama reports, kept apart. Ollama reports the whole prompt as input tokens, cached tokens
included (T2's record), so the input count is the prompt's size for the num_ctx warning:
when it is over 90% of num_ctx, a WARNING naming the role, the prompt tokens, and num_ctx goes
through `logging` (`SPEC.md` Implementation, Models).

Nothing is retried (`SPEC.md` Recovery, forks, and replay, Model errors): a connection error,
an error response from Ollama, a reply langchain-ollama cannot read, or a structured reply that
is not JSON valid against its schema raises LLMError after the one request."""

import json
import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import ollama
from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"

Thinking = bool | str
"""Ollama's `think` value: False, True, or a level such as "medium"."""

KeepAlive = int | str
"""Ollama's `keep_alive`: seconds (0 unloads the model after the request) or a duration such as
"30m"."""

Tool = dict[str, Any] | type | Callable[..., Any] | BaseTool

CallKind = Literal["text", "structured", "tools"]
"""The kind of call, in the run metadata as `kind` (not `call`, which the tool loop uses for its
call index)."""


@dataclass(frozen=True)
class ModelSettings:
    """One role's model call settings, all chosen by the caller."""

    role: str
    model: str
    num_ctx: int
    temperature: float
    thinking: Thinking
    keep_alive: KeepAlive


@dataclass(frozen=True)
class Reply[T]:
    """A call's output with its latency in seconds, the token counts Ollama reported (None when
    it reported none), and the attempt number passed in [R26]."""

    output: T
    latency: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int


class LLMError(Exception):
    """A model call failed: the request did not complete, or a structured reply did not
    parse."""


ClientFor = Callable[[ModelSettings], BaseChatModel]
"""Builds the chat client for one call's settings."""


def ollama_client(settings: ModelSettings) -> ChatOllama:
    """ChatOllama with the settings as given; the endpoint is OLLAMA_BASE_URL, read from `.env`
    when it is not already in the environment, or the local default."""
    load_dotenv()
    return ChatOllama(
        model=settings.model,
        base_url=os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL,
        num_ctx=settings.num_ctx,
        temperature=settings.temperature,
        reasoning=settings.thinking,
        keep_alive=settings.keep_alive,
    )


def _request(
    settings: ModelSettings,
    runnable: Runnable[LanguageModelInput, AIMessage],
    messages: Sequence[BaseMessage],
    attempt: int,
    kind: CallKind,
    metadata: Mapping[str, Any] | None,
) -> tuple[AIMessage, float, int | None, int | None]:
    """Send the one request with the role, attempt, and kind in its run metadata, merged with the
    caller's `metadata` (the wrapper's three keys win); return the message, latency, and input
    and output tokens."""
    run_metadata = {
        **(metadata or {}),
        "role": settings.role,
        "attempt": attempt,
        "kind": kind,
    }
    start = time.perf_counter()
    try:
        message = runnable.invoke(list(messages), config={"metadata": run_metadata})
    except (ConnectionError, httpx.HTTPError, ollama.ResponseError) as e:
        detail = " ".join(str(e).split())
        raise LLMError(
            f"{settings.role}: model call failed: {type(e).__name__}: {detail}"
        ) from e
    except ValueError as e:
        # A reply that cannot be read: a stream line that is not JSON (JSONDecodeError), one the
        # ollama client's response model rejects (pydantic's ValidationError, e.g. tool
        # arguments sent as a string), an empty stream (ChatOllama's ValueError), or tool
        # arguments LangChain cannot parse (OutputParserException).
        detail = " ".join(str(e).split())
        raise LLMError(
            f"{settings.role}: reply did not parse: {type(e).__name__}: {detail}"
        ) from e
    latency = time.perf_counter() - start
    usage = message.usage_metadata
    input_tokens = usage["input_tokens"] if usage else None
    output_tokens = usage["output_tokens"] if usage else None
    if input_tokens is None:
        logger.warning("%s: Ollama reported no token counts", settings.role)
    elif input_tokens * 10 > settings.num_ctx * 9:
        logger.warning(
            "%s: prompt tokens %d are over 90%% of num_ctx %d",
            settings.role,
            input_tokens,
            settings.num_ctx,
        )
    return message, latency, input_tokens, output_tokens


def call_text(
    settings: ModelSettings,
    messages: Sequence[BaseMessage],
    attempt: int,
    client_for: ClientFor = ollama_client,
    metadata: Mapping[str, Any] | None = None,
) -> Reply[str]:
    """A plain-text call; the output is the reply's text. `metadata` is added to the run
    metadata."""
    message, latency, tokens_in, tokens_out = _request(
        settings, client_for(settings), messages, attempt, "text", metadata
    )
    return Reply(message.text, latency, tokens_in, tokens_out, attempt)


def call_structured(
    settings: ModelSettings,
    messages: Sequence[BaseMessage],
    schema: dict[str, Any],
    attempt: int,
    client_for: ClientFor = ollama_client,
    metadata: Mapping[str, Any] | None = None,
) -> Reply[dict[str, Any]]:
    """A structured-output call with `schema` sent as Ollama's `format` and no tool; the output
    is the reply parsed as JSON and valid against `schema`. `metadata` is added to the run
    metadata."""
    runnable = client_for(settings).bind(format=schema)
    message, latency, tokens_in, tokens_out = _request(
        settings, runnable, messages, attempt, "structured", metadata
    )
    try:
        parsed = json.loads(message.text)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict) or not Draft202012Validator(schema).is_valid(parsed):
        raise LLMError(f"{settings.role}: structured reply did not parse: {message.text}")
    return Reply(parsed, latency, tokens_in, tokens_out, attempt)


def call_tools(
    settings: ModelSettings,
    messages: Sequence[BaseMessage],
    tools: Sequence[Tool],
    attempt: int,
    client_for: ClientFor = ollama_client,
    metadata: Mapping[str, Any] | None = None,
) -> Reply[AIMessage]:
    """A call with `tools` bound; the output is the model's message, with its tool calls.
    `metadata` is added to the run metadata."""
    runnable = client_for(settings).bind_tools(list(tools))
    message, latency, tokens_in, tokens_out = _request(
        settings, runnable, messages, attempt, "tools", metadata
    )
    return Reply(message, latency, tokens_in, tokens_out, attempt)
