"""Langfuse tracing of one game: one game is one trace, one batch is one session (`SPEC.md` M3;
Goals, Evaluation and observability). This module owns every `langfuse` import; the rest of the
program sees a `TracingClient` and the functions here.

The client: `build_client`, called once per game by `play.main`, reads `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL`, loaded with python-dotenv from the repo-root
`.env` as `llm.ollama_client` loads the Ollama endpoint, and passes them to the SDK explicitly
(the SDK does not read `.env`). No tracing has one representation: `build_client` returns None.
When any of the three is missing it logs one warning naming the missing variables and returns
None, and the game runs untraced; the SDK's own fallbacks are never used, since for a missing
key it builds a disabled client that still reads the keys from the environment, and for a
missing base URL it falls back to `LANGFUSE_HOST` and then to Langfuse Cloud, which would send
the prompts off the machine (`docs/DECISIONS.md`, 2026-10-23, rejected Cloud). With wrong keys
the client is built and the exporter logs each rejected export. In every case the game runs to
its end, since the health check before each game is M7's (T2, Q2). The `TracingClient` carries
the public key beside the SDK client because the callback handler finds its client in the SDK's
process-wide registry by that key, and the SDK client does not expose the key it holds; the
tests register several in-memory clients in one process.

The trace: `game_span` wraps one game in a span named by the card id, the trace's root, and
propagates the session id and the trace name (the card id, also in the trace metadata) to every
span under it. The session id is the name of the output file's parent directory after the path
is resolved (`session_id`), so `out.json` in the current directory gets that directory's name,
a game run by hand into `runs/t14/` lands in session `t14`, and a batch's records written next
to its manifest (BACKLOG M7) share one session; the one-game command gains no parameter (T2,
Q1).

The spans: node A runs before the graph and gets no span from the callback handler, so
`node_a_span` makes one named `A`; the graph's nodes get chain spans named by their node names
(G, B, C, D, E, F; the node table in `SPEC.md` Full flow of one game) from the LangChain
callback handler (`callback_handler`) passed in the graph's config, which also makes one
generation span per model call and one tool span per run of the search tool. The per-call
metadata on those spans (attempt, role, lookup index) is T3's.

The flush: `flush` sends what the SDK has buffered; `play.main` calls it in a `finally`, so a
game stopped by a model error still exports what it has, with the game span ended in error.
`SPEC.md` Recovery, forks, and replay (Trace loss): a trace the stack drops is not a reason to
rerun the game."""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)

NODE_A_SPAN = "A"
VARIABLES = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")


@dataclass(frozen=True)
class TracingClient:
    """The SDK client, built from all three variables, and the public key it was built with."""

    client: Langfuse
    public_key: str


def build_client() -> TracingClient | None:
    """The client from the three `LANGFUSE_*` variables, loaded from `.env` when they are not
    already in the environment and passed to the SDK explicitly; None, after one warning naming
    the missing variables, when any is missing, so the game runs untraced. The SDK is never
    left to fill a gap: given no key it reads `LANGFUSE_PUBLIC_KEY` from the environment itself,
    and given no base URL it falls back to `LANGFUSE_HOST` and then to Langfuse Cloud."""
    load_dotenv()
    values = {name: os.environ.get(name) for name in VARIABLES}
    missing = [name for name, value in values.items() if value is None]
    if missing:
        consequence = "the game runs untraced"
        if "LANGFUSE_BASE_URL" in missing:
            consequence += " (with no base URL the SDK would fall back to Langfuse Cloud)"
        logger.warning("%s not set: %s", ", ".join(missing), consequence)
        return None
    public_key, secret_key, base_url = (values[name] for name in VARIABLES)
    assert public_key is not None and secret_key is not None and base_url is not None
    client = Langfuse(public_key=public_key, secret_key=secret_key, base_url=base_url)
    return TracingClient(client, public_key)


def session_id(output: Path) -> str:
    """The session of a game written to `output`: its parent directory's name after resolving
    the path, never an empty string."""
    return output.resolve().parent.name


@contextmanager
def game_span(tracing: TracingClient, card_id: str, session: str) -> Iterator[None]:
    """One game as one trace: a root span named by the card id, with the session id, the trace
    name, and the card id in the trace metadata propagated to every span inside. An exception
    inside ends the span with an error status."""
    with propagate_attributes(
        session_id=session, trace_name=card_id, metadata={"card_id": card_id}
    ):
        with tracing.client.start_as_current_observation(name=card_id, as_type="span"):
            yield


@contextmanager
def node_a_span(tracing: TracingClient) -> Iterator[None]:
    """The span of node A, which runs before the graph and so outside the callback handler."""
    with tracing.client.start_as_current_observation(name=NODE_A_SPAN, as_type="span"):
        yield


def callback_handler(tracing: TracingClient) -> BaseCallbackHandler:
    """The LangChain callback handler for the graph's config, bound to `tracing`'s client."""
    return CallbackHandler(public_key=tracing.public_key)


def flush(tracing: TracingClient) -> None:
    """Send what the SDK has buffered."""
    tracing.client.flush()
