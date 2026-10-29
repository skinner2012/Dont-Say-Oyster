"""Reading the spans a game exports into the in-memory exporter, shared by the game tests of
`tests/test_play.py` and `tests/test_tracing.py`. The SDK's attribute keys were read off the
exported spans of the smoke test, not from its code."""

import json
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan

OBSERVATION_TYPE = "langfuse.observation.type"
METADATA = "langfuse.observation.metadata."  # + the run metadata key; values JSON-encoded


def of_type(spans: list[ReadableSpan], observation_type: str) -> list[ReadableSpan]:
    return [s for s in spans if attribute(s, OBSERVATION_TYPE) == observation_type]


def attribute(span: ReadableSpan, key: str) -> Any:
    return (span.attributes or {}).get(key)


def metadata(span: ReadableSpan, key: str) -> Any:
    """A run metadata value on `span`, decoded; None when the span does not carry it."""
    value = attribute(span, METADATA + key)
    return None if value is None else json.loads(value)


def key(span: ReadableSpan) -> tuple[Any, Any]:
    return metadata(span, "round"), metadata(span, "call")


def in_order(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    return sorted(spans, key=lambda s: s.start_time or 0)
