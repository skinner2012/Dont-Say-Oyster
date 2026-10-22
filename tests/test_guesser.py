"""Node E (the Guesser) with scripted replies on the committed card 烤蚵仔 and the committed corpus
(T12 Acceptance): the prompt and its isolation, the tool loop [R43], the structured call [R47],
and the invalid-question loop [R17].

The scripted client answers each call from a fixed list (an AIMessage with tool calls for the
loop, JSON text for the structured calls); the wrapper functions E calls are wrapped by a spy
that keeps each call's messages, what was bound, its attempt number, and its Reply."""

import json
from pathlib import Path
from typing import Any, Literal, get_type_hints

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from dont_say_oyster import guesser
from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, Card, load_cards
from dont_say_oyster.corpus import CorpusEntry, load_corpus
from dont_say_oyster.guesser import (
    GUESS_ONLY_SCHEMA,
    PROMPT_PATH,
    QUESTION_OR_GUESS_SCHEMA,
    build_prompt,
    node_e,
    route_after_e,
)
from dont_say_oyster.llm import ModelSettings, Reply, call_structured, call_tools
from dont_say_oyster.program_nodes import node_a, node_g
from dont_say_oyster.prompt_sections import sections
from dont_say_oyster.state import PROGRAM_ONLY, Lookup, State
from tests.test_llm import Clients, reply, scripted

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"
CARD_ID = "card-5ed17f8f"
SETTINGS = ModelSettings("Guesser", "gemma4:26b-a4b-it-q4_K_M", 16384, 0.7, False, "30m")
SECTIONS = sections(PROMPT_PATH)
FIXED = SECTIONS["fixed message [R17]"]
BLOCKED = SECTIONS["blocked lookup result"]
DESCRIPTION = "A seafood snack cooked over open fire at night-market stalls."
INVALID = "Is it like an oyster omelet?"  # 蚵仔煎 is a distractor; its English names include it
VALID = "Is it eaten with a dipping sauce?"


@pytest.fixture(scope="module")
def corpus() -> list[CorpusEntry]:
    return load_corpus(CORPUS_PATH)


@pytest.fixture(scope="module")
def cards(corpus: list[CorpusEntry]) -> list[Card]:
    return load_cards(CARDS_PATH, corpus)


@pytest.fixture
def start(cards: list[Card]) -> State:
    """Round 1 as E sees it: G has run and C (or D) has filled the Guesser's row."""
    return with_input(node_g(node_a(CARD_ID, cards)), DESCRIPTION)


def with_input(
    state: State, text: str, kind: Literal["description", "answer"] = "description"
) -> State:
    """What C and D leave for E: the Guesser's row filled and the text appended to the earlier
    descriptions and answers."""
    return {
        **state,
        "guesser_input": {
            "kind": kind,
            "text": text,
            "latency": 1.0,
            "input_tokens": 100,
            "output_tokens": 20,
            "attempt": 1,
        },
        "earlier_texts": [*state["earlier_texts"], {"round": state["round"], "kind": kind,
                                                    "text": text}],
    }


def tool_reply(*calls: dict[str, Any]) -> AIMessage:
    """A tool-loop reply carrying one search call per argument dict, in order."""
    return reply(
        "",
        300,
        20,
        tool_calls=[
            {"name": "search", "args": args, "id": f"call-{n}", "type": "tool_call"}
            for n, args in enumerate(calls, 1)
        ],
    )


def guess(text: str, confidence: float = 0.8) -> AIMessage:
    return reply(json.dumps({"kind": "guess", "text": text, "confidence": confidence},
                            ensure_ascii=False), 400, 15)


def question(text: str, confidence: float = 0.5) -> AIMessage:
    return reply(json.dumps({"kind": "question", "text": text, "confidence": confidence}), 400, 15)


class Call:
    """One wrapper call E made: which wrapper, the messages sent, what was bound, the attempt
    number passed, and the Reply returned."""

    def __init__(self, kind: str, messages: list[BaseMessage], bound: Any, attempt: int) -> None:
        self.kind = kind
        self.messages = messages
        self.bound = bound
        self.attempt = attempt
        self.result: Reply[Any] | None = None


class Spy:
    """Wraps the wrapper functions E calls and keeps every call."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[Call] = []
        real_tools, real_structured = call_tools, call_structured

        def spy_tools(
            settings: Any, messages: Any, tools: Any, attempt: int, client_for: Any
        ) -> Any:
            call = Call("tools", list(messages), list(tools), attempt)
            self.calls.append(call)
            call.result = real_tools(settings, messages, tools, attempt, client_for)
            return call.result

        def spy_structured(
            settings: Any, messages: Any, schema: Any, attempt: int, client_for: Any
        ) -> Any:
            call = Call("structured", list(messages), schema, attempt)
            self.calls.append(call)
            call.result = real_structured(settings, messages, schema, attempt, client_for)
            return call.result

        monkeypatch.setattr(guesser, "call_tools", spy_tools)
        monkeypatch.setattr(guesser, "call_structured", spy_structured)

    @property
    def kinds(self) -> list[str]:
        return [c.kind for c in self.calls]

    @property
    def attempts(self) -> list[int]:
        return [c.attempt for c in self.calls]

    @property
    def structured(self) -> list[Call]:
        return [c for c in self.calls if c.kind == "structured"]


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    return Spy(monkeypatch)


def run(state: State, corpus: list[CorpusEntry], *replies: AIMessage) -> tuple[State, Clients]:
    clients = Clients(scripted(*replies))
    return node_e(state, SETTINGS, corpus, clients), clients


def tool_messages(call: Call) -> list[ToolMessage]:
    return [m for m in call.messages if isinstance(m, ToolMessage)]


def found(lookup: Lookup) -> dict[str, Any]:
    """The result JSON of a lookup that was searched."""
    assert isinstance(lookup["result"], dict) and lookup["status"] == "success"
    return lookup["result"]


# The prompt.


def test_sections_are_parsed_from_the_prompt_file() -> None:
    assert set(SECTIONS) == {
        "prompt",
        "task: question or guess",
        "task: guess only",
        "fixed message [R17]",
        "blocked lookup result",
        "conventions",
    }
    assert FIXED.startswith("Your question was not accepted")
    assert BLOCKED.startswith("This search was not run")


def test_the_prompt_holds_only_the_guessers_items(start: State) -> None:
    """Isolation: every row holds a distinct sentinel; the prompt holds the Guesser's items
    (Information isolation) and none of the others, and no section meant for later."""
    state: State = {
        **start,
        "card_id": "SENTINEL-card-id",
        "names": ["SENTINEL-name", "SENTINEL-alias"],
        "english_names": ["SENTINEL-english"],
        "forbidden_words": ["SENTINEL-forbidden"],
        "attributes": {"dish_type": ["SENTINEL-attribute"]},
        "distractors": ["SENTINEL-distractor"],
        "guesser_input": {
            "kind": "answer", "text": "SENTINEL-this-round", "latency": 1.0,
            "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "description": {
            "description": "SENTINEL-description-row", "latency": 1.0, "input_tokens": 1,
            "output_tokens": 1, "attempt": 1,
        },
        "answer": {
            "answer": "SENTINEL-answer-row", "latency": 1.0, "input_tokens": 1,
            "output_tokens": 1, "attempt": 1,
        },
        "guesser_output": {
            "kind": "guess", "text": "SENTINEL-last-output", "confidence": 0.5, "latency": 1.0,
            "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "verdict": {
            "verdict": "fail", "reason": "SENTINEL-verdict", "latency": 1.0, "input_tokens": 1,
            "output_tokens": 1, "attempt": 1,
        },
        "earlier_texts": [
            {"round": 1, "kind": "description", "text": "SENTINEL-earlier-description"},
            {"round": 2, "kind": "answer", "text": "SENTINEL-earlier-answer"},
            {"round": 3, "kind": "answer", "text": "SENTINEL-this-round"},
        ],
        "rejected": [{"round": 1, "description": "SENTINEL-rejected", "reason": "SENTINEL-reason"}],
        "earlier_guesses": [
            {"round": 1, "kind": "guess", "text": "SENTINEL-earlier-guess", "confidence": 0.7},
            {"round": 2, "kind": "question", "text": "SENTINEL-earlier-question",
             "confidence": None},
        ],
        "lookups": [{
            "round": 2, "call": 1, "name": "search",
            "arguments": {"keywords": ["SENTINEL-lookup"]}, "result": "SENTINEL-lookup-result",
            "status": "error", "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
            "attempt": 1,
        }],
        "round": 3,
        "questions": 1,
        "guess_only": False,
    }
    prompt = build_prompt(state)
    for shown in (
        "SENTINEL-this-round",
        "SENTINEL-earlier-description",
        "SENTINEL-earlier-answer",
        "SENTINEL-earlier-guess",
        "SENTINEL-earlier-question",
        "round 3 of ten",
        "Questions asked so far: 1 of three",
    ):
        assert shown in prompt
    for hidden in (
        "SENTINEL-card-id", "SENTINEL-name", "SENTINEL-alias", "SENTINEL-english",
        "SENTINEL-forbidden", "SENTINEL-attribute", "SENTINEL-distractor",
        "SENTINEL-description-row", "SENTINEL-answer-row", "SENTINEL-last-output",
        "SENTINEL-verdict", "SENTINEL-rejected", "SENTINEL-reason", "SENTINEL-lookup",
    ):
        assert hidden not in prompt
    assert prompt.count("SENTINEL-this-round") == 1  # this round's item is not in the earlier list
    for section in ("fixed message [R17]", "blocked lookup result", "conventions"):
        assert SECTIONS[section] not in prompt
    assert "{" not in prompt and "}" not in prompt
    assert set(PROGRAM_ONLY) <= set(state)  # the sentinel State is a whole State


def test_empty_slots_print_none_and_the_task_asks_for_a_question_or_guess(start: State) -> None:
    prompt = build_prompt(start)
    assert "This is round 1 of ten. Questions asked so far: 0 of three." in prompt
    assert prompt.count("(none)") == 2
    assert DESCRIPTION in prompt
    assert prompt.rstrip().endswith(SECTIONS["task: question or guess"])
    assert SECTIONS["task: guess only"] not in prompt


def test_with_the_guess_only_flag_the_task_says_guess_only(start: State) -> None:
    prompt = build_prompt({**start, "guess_only": True})
    assert prompt.rstrip().endswith(SECTIONS["task: guess only"])
    assert SECTIONS["task: question or guess"] not in prompt


def test_the_prompt_file_is_the_committed_one() -> None:
    assert PROMPT_PATH == Path(__file__).resolve().parents[1] / "prompts" / "guesser.txt"


# The tool loop [R43], [R49].


def test_two_lookups_then_none_give_two_results_and_one_structured_call(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, clients = run(
        start, corpus,
        tool_reply({"main_ingredients": ["Seafood"], "cooking_method": ["Grilled"]}),
        tool_reply({"keywords": ["oyster"]}),
        tool_reply(),
        guess("烤蚵仔"),
    )
    assert spy.kinds == ["tools", "tools", "tools", "structured"]
    assert state["lookup_count"] == 2
    assert [lookup["round"] for lookup in state["lookups"]] == [1, 1]
    assert state["lookups"][0]["arguments"] == {
        "main_ingredients": ["Seafood"], "cooking_method": ["Grilled"],
    }
    first = [hit["official_name"] for hit in found(state["lookups"][0])["results"]]
    assert "烤蚵仔" in first and "烤魷魚" in first
    assert found(state["lookups"][0])["more_results"] is False
    assert state["lookups"][1]["arguments"] == {"keywords": ["oyster"]}
    second = [hit["official_name"] for hit in found(state["lookups"][1])["results"]]
    assert {"烤蚵仔", "蚵仔煎", "蚵嗲", "蚵仔酥"} <= set(second)
    # Each tool-bound call binds the search tool and nothing else; the structured call binds no
    # tool and sends the schema as Ollama's format.
    for request in clients.model.requests[:3]:
        assert [tool.name for tool in request["tools"]] == ["search"]
        assert "format" not in request
    assert clients.model.requests[3] == {"format": QUESTION_OR_GUESS_SCHEMA}
    (structured,) = spy.structured
    assert structured.bound == QUESTION_OR_GUESS_SCHEMA
    # The structured call sees the whole history: prompt, calls, results.
    history = structured.messages
    assert isinstance(history[0], HumanMessage) and history[0].text == build_prompt(start)
    assert [type(m).__name__ for m in history] == [
        "HumanMessage", "AIMessage", "ToolMessage", "AIMessage", "ToolMessage", "AIMessage",
    ]
    assert json.loads(history[2].text) == state["lookups"][0]["result"]
    assert isinstance(history[2], ToolMessage) and history[2].tool_call_id == "call-1"


def test_six_lookup_requests_run_five_and_block_the_sixth(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(
        start, corpus,
        *[tool_reply({"keywords": [word]}) for word in
          ("oyster", "squid", "snail", "fritter", "omelet", "grilled")],
        guess("烤蚵仔"),
    )
    assert spy.kinds == ["tools"] * 6 + ["structured"]
    assert state["lookup_count"] == 5
    assert [lookup["arguments"] for lookup in state["lookups"]] == [
        {"keywords": [w]} for w in ("oyster", "squid", "snail", "fritter", "omelet")
    ]
    history = spy.structured[0].messages
    results = tool_messages(spy.structured[0])
    assert len(results) == 6
    assert results[5].text == BLOCKED and results[5].tool_call_id == "call-1"
    assert all(m.text != BLOCKED for m in results[:5])
    assert isinstance(history[-1], ToolMessage) and history[-1].text == BLOCKED


def test_a_reply_with_three_calls_after_three_lookups_runs_two_and_blocks_the_third(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(
        start, corpus,
        tool_reply({"keywords": ["oyster"]}),
        tool_reply({"keywords": ["squid"]}),
        tool_reply({"keywords": ["snail"]}),
        tool_reply({"keywords": ["fritter"]}, {"keywords": ["omelet"]}, {"keywords": ["grilled"]}),
        guess("烤蚵仔"),
    )
    assert spy.kinds == ["tools"] * 4 + ["structured"]
    assert state["lookup_count"] == 5
    assert [lookup["arguments"]["keywords"] for lookup in state["lookups"]] == [
        ["oyster"], ["squid"], ["snail"], ["fritter"], ["omelet"],
    ]
    results = tool_messages(spy.structured[0])
    assert [m.tool_call_id for m in results] == [
        "call-1", "call-1", "call-1", "call-1", "call-2", "call-3",
    ]
    assert json.loads(results[4].text)["results"][0]["official_name"] == "蚵仔煎"
    assert results[5].text == BLOCKED
    assert "grilled" not in json.dumps([lookup["arguments"] for lookup in state["lookups"]])


@pytest.mark.parametrize(
    ("args", "problem"),
    [
        ({"main_ingredients": ["Oysters"]}, "main_ingredients[0]"),
        ({}, "give at least one filter or keyword"),
    ],
    ids=["value-outside-list", "no-filter-no-keyword"],
)
def test_a_rejected_call_counts_as_one_lookup_with_the_validation_message(
    start: State, corpus: list[CorpusEntry], spy: Spy, args: dict[str, Any], problem: str
) -> None:
    state, _ = run(start, corpus, tool_reply(args), tool_reply(), guess("烤蚵仔"))
    assert state["lookup_count"] == 1
    (lookup,) = state["lookups"]
    assert lookup["arguments"] == args
    assert lookup["status"] == "error"
    assert isinstance(lookup["result"], str)
    assert lookup["result"].startswith("The search was not run; the tool's schema rejects")
    assert problem in lookup["result"]
    (result,) = tool_messages(spy.structured[0])
    assert result.text == lookup["result"] and result.status == "error"


def test_lookups_from_earlier_rounds_are_kept_and_the_counter_is_this_rounds(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    earlier: Lookup = {
        "round": 0, "call": 1, "name": "search", "arguments": {"keywords": ["x"]},
        "result": "earlier", "status": "error", "latency": 0.5, "input_tokens": 1,
        "output_tokens": 1, "attempt": 1,
    }
    state, _ = run(
        {**start, "lookups": [earlier]}, corpus, tool_reply({"keywords": ["oyster"]}),
        tool_reply(), guess("烤蚵仔"),
    )
    assert state["lookups"][0] == earlier
    assert len(state["lookups"]) == 2 and state["lookup_count"] == 1


# The structured call [R47], [R48] and its outcomes.


def test_a_guess_reaches_f_and_is_written_to_earlier_guesses(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(start, corpus, tool_reply(), guess("烤蚵仔", 0.8))
    assert route_after_e(state) == "F"
    assert state["guesser_output"] == {
        "kind": "guess", "text": "烤蚵仔", "confidence": 0.8, "latency": pytest.approx(0, abs=1),
        "input_tokens": 400, "output_tokens": 15, "attempt": 1,
    }
    assert state["earlier_guesses"] == [
        {"round": 1, "kind": "guess", "text": "烤蚵仔", "confidence": 0.8}
    ]
    assert state["owes"] == "description"
    assert state["violation"] is None
    assert state["questions"] == 0 and state["round"] == 1


def test_a_guess_without_chinese_is_still_a_guess_for_f(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(start, corpus, tool_reply(), guess("grilled oyster", 0.4))
    assert route_after_e(state) == "F"
    assert state["guesser_output"] is not None
    assert state["guesser_output"]["kind"] == "guess"
    assert state["earlier_guesses"][-1]["text"] == "grilled oyster"


def test_a_valid_question_counts_one_question_and_reaches_g(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(start, corpus, tool_reply(), question(VALID))
    assert route_after_e(state) == "G"
    assert state["questions"] == 1
    assert state["guesser_output"] == {
        "kind": "question", "text": VALID, "confidence": None,
        "latency": pytest.approx(0, abs=1), "input_tokens": 400, "output_tokens": 15,
        "attempt": 1,
    }
    assert state["earlier_guesses"] == [
        {"round": 1, "kind": "question", "text": VALID, "confidence": None}
    ]
    assert state["owes"] == "answer"
    assert state["invalid_questions"] == 0


def test_two_invalid_questions_then_a_valid_one_repeat_only_the_structured_call(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, clients = run(
        start, corpus,
        tool_reply({"keywords": ["oyster"]}), tool_reply(),
        question(INVALID), question(INVALID), question(VALID),
    )
    assert route_after_e(state) == "G"
    assert state["questions"] == 1
    assert state["round"] == 1
    assert state["earlier_guesses"] == [
        {"round": 1, "kind": "question", "text": VALID, "confidence": None}
    ]
    assert state["guesser_output"] is not None
    assert state["guesser_output"]["text"] == VALID
    assert state["guesser_output"]["attempt"] == 3
    assert state["invalid_questions"] == 2
    assert state["lookup_count"] == 1
    # No tool-bound call after the first invalid question: on the wire and at the wrapper.
    assert spy.kinds == ["tools", "tools", "structured", "structured", "structured"]
    assert all("tools" not in request for request in clients.model.requests[2:])
    assert spy.attempts == [1, 1, 1, 2, 3]
    first, second, third = spy.structured
    assert [type(m).__name__ for m in first.messages] == [
        "HumanMessage", "AIMessage", "ToolMessage", "AIMessage",
    ]
    # Each retry adds the invalid reply as the model's message and the fixed message after it.
    assert [type(m).__name__ for m in second.messages[-2:]] == ["AIMessage", "HumanMessage"]
    assert json.loads(second.messages[-2].text)["text"] == INVALID
    assert second.messages[-1].text == FIXED
    assert [type(m).__name__ for m in third.messages[-4:]] == [
        "AIMessage", "HumanMessage", "AIMessage", "HumanMessage",
    ]
    assert third.messages[-1].text == FIXED
    assert len(third.messages) == len(first.messages) + 4
    assert FIXED not in first.messages[0].text


def test_a_chinese_question_and_a_card_english_name_are_invalid(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(
        start, corpus, tool_reply(),
        question("Is it 烤的?"), question("Is it a grilled oyster?"), question(VALID),
    )
    assert spy.attempts == [1, 1, 2, 3]
    assert state["questions"] == 1 and route_after_e(state) == "G"


def test_a_guess_on_the_retry_is_accepted(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(start, corpus, tool_reply(), question(INVALID), guess("烤蚵仔", 0.9))
    assert route_after_e(state) == "F"
    assert state["questions"] == 0
    assert state["guesser_output"] is not None
    assert state["guesser_output"]["attempt"] == 2
    assert state["guesser_output"]["kind"] == "guess"
    assert state["earlier_guesses"] == [
        {"round": 1, "kind": "guess", "text": "烤蚵仔", "confidence": 0.9}
    ]


def test_three_invalid_questions_reach_f_as_a_guesser_violation(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(
        start, corpus, tool_reply(), question(INVALID), question(INVALID), question(INVALID),
    )
    assert route_after_e(state) == "F"
    assert state["violation"] == "Guesser"
    assert state["questions"] == 0
    assert state["earlier_guesses"] == []
    assert state["invalid_questions"] == 3
    assert spy.attempts == [1, 1, 2, 3]
    assert spy.kinds == ["tools", "structured", "structured", "structured"]
    assert state["guesser_output"] is not None
    assert state["guesser_output"]["kind"] == "question"
    assert state["guesser_output"]["attempt"] == 3


def test_the_next_round_starts_its_calls_at_attempt_one(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(start, corpus, tool_reply(), question(INVALID), question(VALID))
    assert spy.attempts == [1, 1, 2]
    next_round = with_input(node_g(state), "Yes, with a sauce on the side.", "answer")
    assert next_round["round"] == 2
    state, _ = run(next_round, corpus, tool_reply({"keywords": ["oyster"]}), tool_reply(),
                   guess("烤蚵仔"))
    assert spy.attempts[3:] == [1, 1, 1]
    assert state["lookup_count"] == 1
    assert state["lookups"][-1]["round"] == 2
    assert state["earlier_guesses"] == [
        {"round": 1, "kind": "question", "text": VALID, "confidence": None},
        {"round": 2, "kind": "guess", "text": "烤蚵仔", "confidence": 0.8},
    ]


def test_with_the_guess_only_flag_the_schema_has_no_question(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    only: State = {**start, "guess_only": True}
    state, clients = run(
        only, corpus, tool_reply(),
        reply(json.dumps({"text": "烤蚵仔", "confidence": 0.6}, ensure_ascii=False), 400, 15),
    )
    (structured,) = spy.structured
    assert structured.bound == GUESS_ONLY_SCHEMA
    assert clients.model.requests[-1] == {"format": GUESS_ONLY_SCHEMA}
    assert "kind" not in GUESS_ONLY_SCHEMA["properties"]
    assert "question" not in json.dumps(GUESS_ONLY_SCHEMA)
    assert GUESS_ONLY_SCHEMA["required"] == ["text", "confidence"]
    assert QUESTION_OR_GUESS_SCHEMA["required"] == ["kind", "text", "confidence"]
    assert QUESTION_OR_GUESS_SCHEMA["properties"]["kind"]["enum"] == ["question", "guess"]
    assert route_after_e(state) == "F"
    assert state["guesser_output"] is not None
    assert state["guesser_output"]["kind"] == "guess"
    assert state["guesser_output"]["confidence"] == 0.6
    assert structured.messages[0].text.rstrip().endswith(SECTIONS["task: guess only"])


def test_every_call_carries_latency_tokens_and_the_attempt_number(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(
        start, corpus,
        tool_reply({"keywords": ["oyster"]}), tool_reply(),
        question(INVALID), question(VALID),
    )
    assert spy.kinds == ["tools", "tools", "structured", "structured"]
    for call in spy.calls:
        assert call.result is not None
        assert call.result.latency >= 0
        assert call.result.input_tokens is not None and call.result.output_tokens is not None
        assert call.result.attempt == call.attempt
    assert spy.attempts == [1, 1, 1, 2]
    # The tool-loop call's metrics are kept with the lookup it produced.
    (lookup,) = state["lookups"]
    assert (lookup["input_tokens"], lookup["output_tokens"], lookup["attempt"]) == (300, 20, 1)
    assert lookup["latency"] >= 0
    assert lookup["call"] == 1
    assert lookup["name"] == "search"
    assert set(lookup) == set(get_type_hints(Lookup))


def test_no_tool_call_at_all_goes_straight_to_the_structured_call(
    start: State, corpus: list[CorpusEntry], spy: Spy
) -> None:
    state, _ = run(start, corpus, reply("I will guess.", 300, 5), guess("烤蚵仔"))
    assert spy.kinds == ["tools", "structured"]
    assert state["lookups"] == [] and state["lookup_count"] == 0
    assert [type(m).__name__ for m in spy.structured[0].messages] == ["HumanMessage", "AIMessage"]
