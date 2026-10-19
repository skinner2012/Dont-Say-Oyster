"""Model checks on Ollama.

`uv run check-models structured [--repeat N]`: each role's
model gets the same structured-output request `--repeat` times with thinking off and then on,
and the command prints each call's latency, how many replies parsed, one parsed object, and the
raw text of every reply that did not parse. It then sends one prompt twice to the Guesser's
model and prints the prompt token count Ollama reports each time. It exits 1 when some model
has no parsed reply under some thinking setting.

The reply's shape is enforced by Ollama's structured output: the request carries the role's
JSON schema as `format` (LangChain's `with_structured_output`, method `json_schema`); no prompt
asks for JSON. A reply counts as parsed when its text is JSON that validates against the
schema. These are check schemas; the game nodes define their own.

`uv run check-models tools [--repeat N]`: the Guesser's model gets a request with a stand-in
search tool bound [R44], `--repeat` times with thinking off and then on. The program runs each
tool call the model makes (the stand-in returns a fixed two-entry result and does not search)
and sends the results back in a separate structured-output call with no tool bound, for a guess
and a confidence [R47], [R48]. For each tool call it prints the arguments as Ollama returned
them and whether each filter value equals a listed value exactly. It exits 1 when, under some
thinking setting, no run made a tool call whose following guess call parsed."""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from jsonschema import Draft202012Validator
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from dont_say_oyster.corpus import SCHEMA_PATH

if TYPE_CHECKING:
    from langchain_core.language_models import LanguageModelInput
    from langchain_core.runnables import Runnable

TEMPERATURE = 0.7
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_REPEAT = 5

Think = bool | str
"""Ollama's `think` value: False, True, or a level such as "medium"."""


@dataclass(frozen=True)
class Model:
    """One role's model as T1 recorded it, with its check schema and prompt and the `think`
    values sent for thinking off and on."""

    role: str
    tag: str
    num_ctx: int
    think_off: Think
    think_on: Think
    schema: dict[str, Any]
    prompt: str


# [R32]
DESCRIBER = Model(
    role="describer",
    tag="qwen3.8:27b-q4_K_M",
    num_ctx=8192,
    think_off=False,
    # Qwen 3.8 takes levels (false, low, medium, xhigh); on is its default level.
    think_on="medium",
    schema={
        "type": "object",
        "required": ["text"],
        "additionalProperties": False,
        "properties": {"text": {"type": "string"}},
    },
    prompt=(
        "You are describing a Taiwanese snack so that someone can guess it. The snack is "
        "珍珠奶茶 (bubble milk tea). Describe it in three or four English sentences without "
        "naming it."
    ),
)

# [R39], [R40]; a reason given with a pass is dropped by parse_reply.
CHALLENGER = Model(
    role="challenger",
    tag="gemma4:12b-it-q4_K_M",
    num_ctx=4096,
    think_off=False,
    think_on=True,
    schema={
        "type": "object",
        "required": ["verdict"],
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
            "reason": {"type": "string"},
        },
    },
    prompt=(
        "Judge whether a description of a Taiwanese snack leads to the snack 珍珠奶茶 (bubble "
        "milk tea) and does not also point to 粉圓冰 (shaved ice with tapioca pearls) or "
        "仙草奶凍 (grass jelly milk pudding). Give a verdict, pass or fail; with a fail, give "
        "the reason in English.\n\nDescription: A sweet cold drink of black tea and milk. Chewy "
        "dark balls sit at the bottom and come up through a wide straw. It was first sold in "
        "Taichung tea shops."
    ),
)

# [R48]
GUESSER = Model(
    role="guesser",
    tag="gemma4:26b-a4b-it-q4_K_M",
    num_ctx=16384,
    think_off=False,
    think_on=True,
    schema={
        "type": "object",
        "required": ["kind", "text", "confidence"],
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["question", "guess"]},
            "text": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
    prompt=(
        "You are guessing a Taiwanese snack from a description. Either ask one yes-or-no "
        "question about it or guess its Chinese name, and give your confidence from 0 to 1.\n\n"
        "Description: A sweet cold drink of black tea and milk. Chewy dark balls sit at the "
        "bottom and come up through a wide straw. It was first sold in Taichung tea shops."
    ),
)

MODELS = (DESCRIBER, CHALLENGER, GUESSER)

# Sent twice to the Guesser's model to see whether the second prompt token count drops when
# Ollama reuses its cache. It shares no opening words with the check prompts.
TOKEN_PROMPT = (
    "Night markets in Taiwan open in the late afternoon and stay busy until after midnight. "
    "Stalls sell grilled sausages, oyster omelettes, fried chicken cutlets, stinky tofu, "
    "scallion pancakes, pepper buns baked in clay ovens, and sweet drinks with chewy pearls. "
    "Visitors walk from stall to stall and share small plates. From this description, either "
    "ask one yes-or-no question about the snack meant or guess its Chinese name, and give your "
    "confidence from 0 to 1."
)


@dataclass(frozen=True)
class Request:
    tag: str
    num_ctx: int
    think: Think
    schema: dict[str, Any]
    prompt: str


@dataclass(frozen=True)
class Reply:
    """The reply's text and the prompt token count Ollama reported (None when it reported
    none)."""

    text: str
    prompt_tokens: int | None


Ask = Callable[[Request], Reply]
"""Sends one structured-output request to the model and returns its reply."""


class ModelError(Exception):
    """A model call failed."""


def parse_reply(model: Model, text: str) -> dict[str, Any] | None:
    """The reply as an object when it is JSON that validates against the model's schema,
    otherwise None. A Challenger reason given with a pass is dropped [R40]."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not Draft202012Validator(model.schema).is_valid(data):
        return None
    if model is CHALLENGER and data["verdict"] == "pass":
        data.pop("reason", None)
    parsed: dict[str, Any] = data
    return parsed


def run_check(model: Model, think: Think, repeat: int, ask: Ask) -> int:
    """Send the model's request `repeat` times with `think`, print each call, the parsed
    count, and one parsed object; return the parsed count."""
    request = Request(model.tag, model.num_ctx, think, model.schema, model.prompt)
    label = f"{model.role} {model.tag} think={think}"
    print(label, flush=True)
    shown: dict[str, Any] | None = None
    parsed = 0
    for n in range(1, repeat + 1):
        start = time.perf_counter()
        reply = ask(request)
        seconds = time.perf_counter() - start
        obj = parse_reply(model, reply.text)
        if obj is None:
            print(f"  call {n}: {seconds:.1f} s, not parsed, raw reply: {reply.text}", flush=True)
        else:
            parsed += 1
            shown = shown or obj
            print(f"  call {n}: {seconds:.1f} s, parsed", flush=True)
    print(f"{label}: {parsed}/{repeat} parsed")
    if shown is not None:
        print(f"  parsed object: {json.dumps(shown, ensure_ascii=False)}")
    return parsed


def run_structured(repeat: int, ask: Ask) -> int:
    """Run every model with thinking off and on, then the prompt-token check; return the exit
    code."""
    failed = []
    for model in MODELS:
        for think in (model.think_off, model.think_on):
            if run_check(model, think, repeat, ask) == 0:
                failed.append(f"{model.role} {model.tag} think={think}")

    request = Request(GUESSER.tag, GUESSER.num_ctx, GUESSER.think_off, GUESSER.schema, TOKEN_PROMPT)
    counts = [ask(request).prompt_tokens for _ in range(2)]
    print(f"prompt tokens, same prompt twice to {GUESSER.tag}: {counts[0]}, {counts[1]}")

    if failed:
        print(f"no parsed reply: {'; '.join(failed)}")
        return 1
    return 0


def base_url(environ: Mapping[str, str]) -> str:
    """The Ollama endpoint: OLLAMA_BASE_URL, or the local default when it is unset or empty."""
    return environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL


def chat_model(request: Request, url: str) -> "Runnable[LanguageModelInput, Any]":
    """The request as a LangChain runnable: ChatOllama at the request's tag, num_ctx, and
    `think` (ChatOllama's `reasoning`), temperature TEMPERATURE, with the schema sent as
    Ollama's `format`. Invoked, it returns {"raw", "parsed", "parsing_error"}."""
    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=request.tag,
        base_url=url,
        num_ctx=request.num_ctx,
        temperature=TEMPERATURE,
        reasoning=request.think,
    )
    return llm.with_structured_output(request.schema, method="json_schema", include_raw=True)


def model_ask() -> Ask:
    """The real model call through langchain-ollama. The endpoint is OLLAMA_BASE_URL, read from
    `.env` when it is not already in the environment. A failed call becomes a one-line
    ModelError."""
    import httpx
    import ollama
    from dotenv import load_dotenv

    load_dotenv()
    url = base_url(os.environ)

    def ask(request: Request) -> Reply:
        try:
            result = chat_model(request, url).invoke(request.prompt)
        except (ollama.ResponseError, ConnectionError, httpx.HTTPError) as e:
            message = " ".join(str(e).split())
            raise ModelError(f"model call failed: {type(e).__name__}: {message}") from e
        raw = result["raw"]
        usage = raw.usage_metadata
        return Reply(raw.text, usage["input_tokens"] if usage else None)

    return ask


# The tools check [R44], [R47], [R48].

FILTER_FIELDS = ("main_ingredients", "cooking_method", "physical_form")


def _listed_values() -> dict[str, list[str]]:
    """Each filter field's values, as `data/corpus/schema.json` lists them."""
    entry = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["items"]
    attributes = entry["properties"]["attributes"]["properties"]
    return {field: attributes[field]["items"]["enum"] for field in FILTER_FIELDS}


LISTED = _listed_values()

# A stand-in with the input shape of [R44]: optional enum filters and an optional keyword list.
# The real tool and its schema are T11's.
SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Search the corpus of Taiwanese snacks. Filter on attribute values, match keywords "
            "against the English names, or both. Returns the matching entries."
        ),
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                **{
                    field: {
                        "type": "array",
                        "items": {"type": "string", "enum": values},
                        "description": f"Entries with at least one of these {field} values.",
                    }
                    for field, values in LISTED.items()
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entries with an English name that matches one of these.",
                },
            },
        },
    },
}

# The stand-in's fixed result: two corpus entries with the fields of [R45].
SEARCH_RESULT = json.dumps(
    [
        {
            "official_name": "黑糖珍珠鮮奶",
            "aliases": ["黑糖波霸鮮奶", "青蛙撞奶"],
            "english_names": ["Brown Sugar Boba Milk"],
            "attributes": {
                "dish_type": ["Drink"],
                "main_ingredients": ["Starch", "Sugar and Sweeteners", "Milk"],
                "cooking_method": ["No Cooking"],
                "flavor": ["Sweet"],
                "physical_form": ["Drink with Add-ins"],
                "occasion": [],
            },
        },
        {
            "official_name": "珍珠奶茶",
            "aliases": ["珍奶", "波霸奶茶", "珍珠鮮奶茶", "波霸鮮奶茶"],
            "english_names": [
                "Bubble Milk Tea",
                "Bubble tea",
                "Pearl milk tea",
                "Zhen Zhu Nai Cha",
                "Bubble Fresh Milk Tea",
            ],
            "attributes": {
                "dish_type": ["Drink"],
                "main_ingredients": ["Tea", "Milk", "Starch"],
                "cooking_method": ["No Cooking"],
                "flavor": ["Sweet"],
                "physical_form": ["Drink with Add-ins"],
                "occasion": [],
            },
        },
    ],
    ensure_ascii=False,
)

# [R48], the guess half: a guess and a confidence.
GUESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["guess", "confidence"],
    "additionalProperties": False,
    "properties": {
        "guess": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

# Its natural filters include values with spaces: Sugar and Sweeteners, Drink with Add-ins,
# No Cooking.
TOOL_PROMPT = (
    "You are guessing a Taiwanese snack from a description. First search the corpus with the "
    "search tool, filtering on what the description tells you. When the search result comes "
    "back, guess the snack's Chinese name and give your confidence from 0 to 1.\n\n"
    "Description: A cold drink of fresh milk with brown sugar syrup streaked down the inside of "
    "the cup. Chewy tapioca balls, simmered in the syrup, sit at the bottom. The stall assembles "
    "it from prepared parts, and you drink it through a wide straw."
)


@dataclass(frozen=True)
class ChatRequest:
    """One chat call: with `tools` bound and no schema, or with no tool and `schema` sent as
    Ollama's `format`."""

    tag: str
    num_ctx: int
    think: Think
    messages: tuple[BaseMessage, ...]
    tools: tuple[dict[str, Any], ...]
    schema: dict[str, Any] | None


@dataclass(frozen=True)
class ChatReply:
    """The model's message as LangChain returns it, and each of its tool calls' arguments as
    Ollama returned them, in order (LangChain rewrites a string argument that parses as a JSON
    list or object)."""

    message: AIMessage
    sent_arguments: tuple[dict[str, Any], ...]


Chat = Callable[[ChatRequest], ChatReply]
"""Sends one chat request to the model and returns its reply."""


def parse_guess(text: str) -> dict[str, Any] | None:
    """The guess call's reply as an object when it is JSON that validates against GUESS_SCHEMA,
    otherwise None."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not Draft202012Validator(GUESS_SCHEMA).is_valid(data):
        return None
    parsed: dict[str, Any] = data
    return parsed


def enum_check(arguments: Mapping[str, Any]) -> list[str]:
    """One line per filter value, saying whether it equals a listed value exactly, and one per
    argument the tool does not take. Keywords have no list and get no line."""
    lines = []
    for name, value in arguments.items():
        if name == "keywords":
            continue
        if name not in LISTED:
            lines.append(f"{name}: not a tool argument")
            continue
        for item in value if isinstance(value, list) else [value]:
            shown = json.dumps(item, ensure_ascii=False)
            listed = "listed" if item in LISTED[name] else "not listed"
            lines.append(f"{name} {shown}: {listed}")
    return lines


def run_tools_check(think: Think, repeat: int, chat: Chat) -> bool:
    """Run the tool call and the guess call `repeat` times with `think` and print each; return
    whether some run made a tool call and then a guess call that parsed."""
    label = f"{GUESSER.role} {GUESSER.tag} think={think}"
    print(label, flush=True)
    called = parsed = both = not_listed = 0
    for n in range(1, repeat + 1):
        messages: list[BaseMessage] = [HumanMessage(TOOL_PROMPT)]
        request = ChatRequest(
            GUESSER.tag, GUESSER.num_ctx, think, tuple(messages), (SEARCH_TOOL,), None
        )
        start = time.perf_counter()
        reply = chat(request)
        seconds = time.perf_counter() - start
        calls = reply.message.tool_calls
        messages.append(reply.message)
        if calls:
            called += 1
            print(f"  run {n}: tool call {seconds:.1f} s, {len(calls)} call(s)", flush=True)
        else:
            print(
                f"  run {n}: tool call {seconds:.1f} s, no tool call, raw reply: "
                f"{reply.message.text}",
                flush=True,
            )
        for call, sent in zip(calls, reply.sent_arguments, strict=True):
            print(f"    {call['name']} {json.dumps(sent, ensure_ascii=False)}")
            if call["args"] != sent:
                print(f"    LangChain args: {json.dumps(call['args'], ensure_ascii=False)}")
            for line in enum_check(sent):
                print(f"      {line}")
                not_listed += not line.endswith(": listed")
            messages.append(ToolMessage(SEARCH_RESULT, tool_call_id=call["id"]))

        request = ChatRequest(
            GUESSER.tag, GUESSER.num_ctx, think, tuple(messages), (), GUESS_SCHEMA
        )
        start = time.perf_counter()
        text = chat(request).message.text
        seconds = time.perf_counter() - start
        guess = parse_guess(text)
        if guess is None:
            print(f"    guess call {seconds:.1f} s, not parsed, raw reply: {text}", flush=True)
        else:
            parsed += 1
            both += bool(calls)
            shown = json.dumps(guess, ensure_ascii=False)
            print(f"    guess call {seconds:.1f} s, parsed: {shown}", flush=True)
    print(
        f"{label}: {called}/{repeat} runs made a tool call, {parsed}/{repeat} guess calls "
        f"parsed, {both} after a tool call; {not_listed} enum values or arguments not listed"
    )
    return both > 0


def run_tools(repeat: int, chat: Chat) -> int:
    """Run the tools check with thinking off and on; return the exit code."""
    failed = [
        f"think={think}"
        for think in (GUESSER.think_off, GUESSER.think_on)
        if not run_tools_check(think, repeat, chat)
    ]
    if failed:
        print(f"no tool call followed by a parsed guess call: {'; '.join(failed)}")
        return 1
    return 0


class _Tee(httpx.SyncByteStream):
    """A response stream that keeps each chunk it passes on."""

    def __init__(self, stream: httpx.SyncByteStream, chunks: list[bytes]) -> None:
        self.stream = stream
        self.chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:
            self.chunks.append(chunk)
            yield chunk

    def close(self) -> None:
        self.stream.close()


class _Tap(httpx.BaseTransport):
    """Passes requests to `inner` and keeps the response bodies, so the tool-call arguments can
    be read as Ollama returned them."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner
        self.chunks: list[bytes] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.inner.handle_request(request)
        assert isinstance(response.stream, httpx.SyncByteStream)
        response.stream = _Tee(response.stream, self.chunks)
        return response

    def tool_call_arguments(self) -> tuple[dict[str, Any], ...]:
        """Each tool call's arguments in the response lines (Ollama streams NDJSON), in order."""
        lines = b"".join(self.chunks).decode("utf-8").splitlines()
        return tuple(
            call["function"]["arguments"]
            for line in lines
            if line.strip()
            for call in json.loads(line).get("message", {}).get("tool_calls") or []
        )


def chat_runnable(
    request: ChatRequest, url: str, transport: httpx.BaseTransport
) -> "Runnable[LanguageModelInput, Any]":
    """The request as a LangChain runnable: ChatOllama as in `chat_model`, over `transport`,
    with the tools bound or, when the request has a schema, the schema sent as Ollama's
    `format` and no tool."""
    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=request.tag,
        base_url=url,
        num_ctx=request.num_ctx,
        temperature=TEMPERATURE,
        reasoning=request.think,
        client_kwargs={"transport": transport},
    )
    if request.schema is not None:
        return llm.with_structured_output(request.schema, method="json_schema", include_raw=True)
    return llm.bind_tools(list(request.tools))


def model_chat(transport: httpx.BaseTransport | None = None) -> Chat:
    """The real chat call through langchain-ollama, over `transport` (httpx's default when None).
    The endpoint is OLLAMA_BASE_URL, read from `.env` when it is not already in the environment.
    A failed call becomes a one-line ModelError."""
    import ollama
    from dotenv import load_dotenv

    load_dotenv()
    url = base_url(os.environ)

    def chat(request: ChatRequest) -> ChatReply:
        tap = _Tap(transport or httpx.HTTPTransport())
        try:
            result = chat_runnable(request, url, tap).invoke(list(request.messages))
        except (ollama.ResponseError, ConnectionError, httpx.HTTPError) as e:
            message = " ".join(str(e).split())
            raise ModelError(f"model call failed: {type(e).__name__}: {message}") from e
        reply = result["raw"] if request.schema is not None else result
        return ChatReply(reply, tap.tool_call_arguments())

    return chat


def _repeat(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def main(
    argv: Sequence[str] | None = None, ask: Ask | None = None, chat: Chat | None = None
) -> int:
    parser = argparse.ArgumentParser(
        prog="check-models", description="Check the three role models on Ollama."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    structured = commands.add_parser(
        "structured", help="check structured output for each model, thinking off and on"
    )
    structured.add_argument(
        "--repeat",
        type=_repeat,
        default=DEFAULT_REPEAT,
        help=f"requests per model and thinking setting (default {DEFAULT_REPEAT})",
    )
    tools = commands.add_parser(
        "tools", help="check tool calling and the separate guess call on the Guesser's model"
    )
    tools.add_argument(
        "--repeat",
        type=_repeat,
        default=DEFAULT_REPEAT,
        help=f"runs per thinking setting (default {DEFAULT_REPEAT})",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "tools":
            return run_tools(args.repeat, chat or model_chat())
        return run_structured(args.repeat, ask or model_ask())
    except ModelError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
