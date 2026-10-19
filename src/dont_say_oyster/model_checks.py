"""Model checks on Ollama. Run as `uv run check-models structured [--repeat N]`: each role's
model gets the same structured-output request `--repeat` times with thinking off and then on,
and the command prints each call's latency, how many replies parsed, one parsed object, and the
raw text of every reply that did not parse. It then sends one prompt twice to the Guesser's
model and prints the prompt token count Ollama reports each time. It exits 1 when some model
has no parsed reply under some thinking setting.

The reply's shape is enforced by Ollama's structured output: the request carries the role's
JSON schema as `format` (LangChain's `with_structured_output`, method `json_schema`); no prompt
asks for JSON. A reply counts as parsed when its text is JSON that validates against the
schema. These are check schemas; the game nodes define their own."""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator

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


def _repeat(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def main(argv: Sequence[str] | None = None, ask: Ask | None = None) -> int:
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
    args = parser.parse_args(argv)
    try:
        return run_structured(args.repeat, ask or model_ask())
    except ModelError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
