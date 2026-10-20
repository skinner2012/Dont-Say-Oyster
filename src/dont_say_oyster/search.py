"""The Guesser's search tool [R44]-[R46]: `search`, a plain function over a validated query, and
`search_tool`, its LangChain tool for `bind_tools`. The filter fields and their values are read
from `data/corpus/schema.json`; the model-facing text (tool, field, and keyword descriptions and
the rejection messages) is `prompts/search_tool.json`.

Schema shape, from T3's record and audit: each filter is `list[Literal[...]]` defaulting to empty,
never an `Optional` (an `anyOf`, which reaches Ollama as `{}` with its enum gone). The ollama
client drops `additionalProperties`, `uniqueItems`, and `minItems`, so what they would say is
checked here, program-side.

A call the schema rejects (a value outside its field's list, an unknown argument, or no filter and
no keyword [R44]) is not searched: the tool returns the validation message as its result and
does not raise (SPEC.md Recovery, forks, and replay, Model errors). Counting lookups is node E's.

Ticket-level readings (T11, answered for the author by the M2 orchestrator, 2026-10-20):
- The result: `search` returns a SearchResult, at most ten hits in corpus order and whether
  more entries matched [R46]; a Hit has no forbidden words [R45]. The tool returns content and
  artifact: the content is the JSON the model reads, `{"results": [...], "more_results": bool}`;
  the artifact is the same SearchResult, so State and what the model saw never differ. A
  rejected call has the validation message as content, no artifact, and status "error". No
  match count: [R46] says only that the output says there are more.
- A value repeated in one field, or a repeated keyword, is searched once, in first-seen order:
  under [R44] it has one meaning, so it is not a wrong call.
- A keyword that is empty after the English normalization [R22] (spaces, apostrophes, and
  punctuation only) is rejected: it would match every English name, the corpus dump [R44]'s
  empty-call rule prevents. A keyword with no Latin letters is searched and matches nothing.
- The field descriptions are SPEC.md Corpus and Cards (Attributes) verbatim, except that each
  heading drops its value list (the enum carries it) and its cardinality ("required, one"), and
  the authoring bullets are left out: the cardinality and those bullets describe corpus entries,
  and in a filter, where every field is an optional list, the Guesser could read them as the
  filter's rule (T11 F1)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from langchain_core.tools import StructuredTool
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    model_validator,
)
from pydantic_core import PydanticCustomError

from dont_say_oyster.corpus import SCHEMA_PATH, Attributes, CorpusEntry
from dont_say_oyster.matching import _english_form, english_contains

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "search_tool.json"

LIMIT = 10


def _attribute_values() -> dict[str, tuple[str, ...]]:
    """Each attribute field's values, in the order `data/corpus/schema.json` lists them."""
    entry = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["items"]
    attributes = entry["properties"]["attributes"]["properties"]
    return {field: tuple(spec["items"]["enum"]) for field, spec in attributes.items()}


VALUES = _attribute_values()
FIELDS = tuple(VALUES)
TEXTS: dict[str, Any] = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _not_empty(keyword: str) -> str:
    """Reject a keyword that T5's English normalization [R22] leaves empty."""
    if not _english_form(keyword):
        raise PydanticCustomError("empty_keyword", TEXTS["messages"]["empty_keyword"])
    return keyword


class _Query(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _filter_or_keyword(self) -> Self:
        if not any(getattr(self, name) for name in type(self).model_fields):
            raise PydanticCustomError(
                "no_filter_or_keyword", TEXTS["messages"]["no_filter_or_keyword"]
            )
        return self


def _list_field(item: Any, description: str) -> Any:
    return (
        Annotated[list[item], AfterValidator(_dedupe)],
        Field(default_factory=list, description=description),
    )


# The query [R44]: one optional filter per attribute field, then the keywords.
SearchQuery: type[BaseModel] = create_model(
    "search",
    __base__=_Query,
    **{
        field: _list_field(Literal[values], TEXTS["fields"][field])
        for field, values in VALUES.items()
    },
    keywords=_list_field(Annotated[str, AfterValidator(_not_empty)], TEXTS["keywords"]),
)


@dataclass(frozen=True)
class Hit:
    """One result [R45]: an entry without its forbidden words."""

    official_name: str
    aliases: tuple[str, ...]
    english_names: tuple[str, ...]
    attributes: Attributes

    def as_json(self) -> dict[str, Any]:
        return {
            "official_name": self.official_name,
            "aliases": list(self.aliases),
            "english_names": list(self.english_names),
            "attributes": {field: list(getattr(self.attributes, field)) for field in FIELDS},
        }


@dataclass(frozen=True)
class SearchResult:
    """At most LIMIT hits in corpus order, and whether more entries matched [R46]."""

    hits: tuple[Hit, ...]
    more: bool

    def as_json(self) -> dict[str, Any]:
        return {"results": [hit.as_json() for hit in self.hits], "more_results": self.more}


def search(corpus: Sequence[CorpusEntry], query: BaseModel) -> SearchResult:
    """The entries that pass every filter given and, when keywords are given, have an English
    name matching one of them [R44]; `query` is a validated SearchQuery."""
    args = dict(query)
    filters = {field: set(args[field]) for field in FIELDS if args[field]}
    keywords: list[str] = args["keywords"]
    matches: list[Hit] = []
    for entry in corpus:
        if not all(filters[f] & set(getattr(entry.attributes, f)) for f in filters):
            continue
        if keywords and not any(english_contains(name, keywords) for name in entry.english_names):
            continue
        matches.append(
            Hit(entry.official_name, entry.aliases, entry.english_names, entry.attributes)
        )
        if len(matches) > LIMIT:
            break
    return SearchResult(tuple(matches[:LIMIT]), len(matches) > LIMIT)


def validation_message(error: ValidationError) -> str:
    """The rejection the model reads: one line per problem, naming the argument and what was
    sent (`main_ingredients[1]: Input should be ... (got 'Boba')`)."""
    lines = [TEXTS["messages"]["rejected"]]
    for problem in error.errors(include_url=False):
        where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in problem["loc"])
        where = where.removeprefix(".")
        lines.append(
            f"{where}: {problem['msg']} (got {problem['input']!r})" if where else problem["msg"]
        )
    return "\n".join(lines)


def search_tool(corpus: Sequence[CorpusEntry]) -> StructuredTool:
    """The search tool over `corpus`, for `bind_tools`. Invoked with a tool call, it returns a
    ToolMessage: the result's JSON as content and the SearchResult as artifact, or the
    validation message with no artifact and status "error"."""

    def run(**args: Any) -> tuple[str, SearchResult]:
        result = search(corpus, SearchQuery.model_validate(args))
        return json.dumps(result.as_json(), ensure_ascii=False), result

    return StructuredTool.from_function(
        func=run,
        name="search",
        description=TEXTS["tool"],
        args_schema=SearchQuery,
        response_format="content_and_artifact",
        handle_validation_error=validation_message,
    )
