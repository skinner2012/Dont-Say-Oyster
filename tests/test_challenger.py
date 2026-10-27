"""Node D (Challenger) and the reject loop with scripted Challenger replies on the committed card
烤蚵仔."""

import json
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatResult

from dont_say_oyster import challenger, llm
from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, load_cards
from dont_say_oyster.challenger import PROMPT_PATH, SCHEMA, build_prompt, node_d, route_after_d
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.llm import ModelSettings, Reply
from dont_say_oyster.program_nodes import node_a, node_g
from dont_say_oyster.prompt_sections import sections
from dont_say_oyster.state import State
from tests.test_llm import Scripted, reply

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"
CARD_ID = "card-5ed17f8f"
SETTINGS = ModelSettings(
    role="challenger",
    model="scripted-challenger",
    num_ctx=4096,
    temperature=0.7,
    thinking=False,
    keep_alive=0,
)
SECTIONS = sections(PROMPT_PATH)
FIXED = SECTIONS["fixed message [R40]"]
FIRST = "Smoky shellfish opened on a grill at a night-market stall, eaten hot in the half shell."
SECOND = "Plump shellfish cooked over a flame until they pop open, served with a squeeze of lime."
THIRD = "Opened over heat and slurped from the shell with a little garlic and chili on top."
ENGLISH = "The detail of a batter coating also fits a fried oyster fritter."
CHINESE = "This also fits 蚵仔煎."


class Recording(Scripted):
    """A scripted chat model that also keeps the messages of each request."""

    sent: list[list[BaseMessage]] = []

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.sent.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


class Challenger:
    """Scripted Challenger replies, each `(verdict, reason)` with its token counts, and the
    attempt number and reply of each wrapper call D makes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *replies: tuple[str, str]) -> None:
        self.model = Recording(
            messages=iter(
                reply(json.dumps({"verdict": v, "reason": r}), 400 + i, 20 + i)
                for i, (v, r) in enumerate(replies)
            ),
            requests=[],
            sent=[],
        )
        self.attempts: list[int] = []
        self.replies: list[Reply[dict[str, Any]]] = []
        call = llm.call_structured

        def spy(*args: Any, **kwargs: Any) -> Reply[dict[str, Any]]:
            result = call(*args, **kwargs)
            self.attempts.append(result.attempt)
            self.replies.append(result)
            return result

        monkeypatch.setattr(challenger, "call_structured", spy)

    def __call__(self, settings: ModelSettings) -> Recording:
        assert settings == SETTINGS
        return self.model

    def d(self, state: State) -> State:
        return node_d(state, SETTINGS, self)


@pytest.fixture(scope="module")
def round_one() -> State:
    cards = load_cards(CARDS_PATH, load_corpus(CORPUS_PATH))
    state = node_g(node_a(CARD_ID, cards))
    assert state["names"] == ["烤蚵仔", "烤牡蠣", "烤生蠔"]
    assert state["distractors"] == ["烤魷魚", "蚵仔酥", "蚵嗲", "蚵仔煎", "燒酒螺"]
    assert state["round"] == 1
    return state


def described(state: State, text: str, attempt: int = 1) -> State:
    """What a scripted B and C leave for D: the description row [R26]."""
    return {
        **state,
        "description": {
            "description": text,
            "latency": 2.5,
            "input_tokens": 900,
            "output_tokens": 70,
            "attempt": attempt,
        },
        "describer_send_backs": attempt - 1,
    }


def test_the_prompt_holds_only_the_names_aliases_distractors_and_description(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    state: State = {
        **round_one,
        "card_id": "S-card-id",
        "names": ["S-official", "S-alias-1", "S-alias-2"],
        "english_names": ["S-english"],
        "forbidden_words": ["S-forbidden"],
        "attributes": {"dish_type": ["S-attribute"]},
        "distractors": ["S-distractor-1", "S-distractor-2"],
        "guesser_input": {"kind": "answer", "text": "S-guesser-input", "latency": 1.0,
                          "input_tokens": 1, "output_tokens": 1, "attempt": 1},
        "description": {"description": "S-description", "latency": 1.0, "input_tokens": 1,
                        "output_tokens": 1, "attempt": 1},
        "answer": {"answer": "S-answer", "latency": 1.0, "input_tokens": 1,
                   "output_tokens": 1, "attempt": 1},
        "guesser_output": {"kind": "question", "text": "S-guesser-output", "confidence": None,
                           "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
                           "attempt": 1},
        "verdict": {"verdict": "fail", "reason": "S-verdict", "latency": 1.0,
                    "input_tokens": 1, "output_tokens": 1, "attempt": 1},
        "earlier_texts": [{"round": 1, "kind": "answer", "text": "S-earlier-text"}],
        "rejected": [{"round": 1, "description": "S-rejected", "reason": "S-rejected-reason"}],
        "earlier_guesses": [{"round": 1, "kind": "guess", "text": "S-earlier-guess",
                             "confidence": 0.5}],
        "lookups": [{"round": 1, "call": 1, "name": "search", "arguments": {}, "result": "S-lookup",
                     "status": "error", "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
                     "attempt": 1}],
        "round": 7771,
        "rejects": 7772,
        "lookup_count": 7773,
        "questions": 7774,
        "forced_passes": 7775,
    }
    model = Challenger(monkeypatch, ("pass", ""))
    model.d(state)

    ((message,),) = model.model.sent
    assert isinstance(message, HumanMessage)
    prompt = message.text
    assert prompt == build_prompt(state, SECTIONS["prompt"])
    for shown in ("S-official", "S-alias-1, S-alias-2", "S-distractor-1, S-distractor-2",
                  "S-description"):
        assert shown in prompt
    for hidden in ("S-card-id", "S-english", "S-forbidden", "S-attribute", "S-guesser-input",
                   "S-answer", "S-guesser-output", "S-verdict", "S-earlier-text", "S-rejected",
                   "S-earlier-guess", "S-lookup", "7771", "7772", "7773", "7774", "7775"):
        assert hidden not in prompt
    assert "===" not in prompt
    assert SECTIONS["re-ask [R40]"] not in prompt


def test_the_prompt_on_the_card_fills_every_slot(round_one: State) -> None:
    prompt = build_prompt(described(round_one, FIRST), SECTIONS["prompt"])
    assert "Official name (Chinese): 烤蚵仔\n" in prompt
    assert "Accepted aliases (Chinese): 烤牡蠣, 烤生蠔\n" in prompt
    assert "(Chinese): 烤魷魚, 蚵仔酥, 蚵嗲, 蚵仔煎, 燒酒螺\n" in prompt
    assert f"The description:\n{FIRST}\n" in prompt
    assert "{" not in prompt


def test_an_empty_slot_prints_none(round_one: State) -> None:
    state: State = {**described(round_one, FIRST), "names": ["烤蚵仔"], "distractors": []}
    prompt = build_prompt(state, SECTIONS["prompt"])
    assert "Accepted aliases (Chinese): (none)\n" in prompt
    assert "must not point to (Chinese): (none)\n" in prompt


def test_a_pass_reaches_e_with_the_description_in_the_guessers_row(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = Challenger(monkeypatch, ("pass", ""))
    after = model.d(described(round_one, FIRST, attempt=2))

    assert route_after_d(after) == "E"
    assert after["guesser_input"] == {
        "kind": "description", "text": FIRST, "latency": 2.5, "input_tokens": 900,
        "output_tokens": 70, "attempt": 2,
    }
    assert after["earlier_texts"] == [{"round": 1, "kind": "description", "text": FIRST}]
    (first,) = model.replies
    assert after["verdict"] == {
        "verdict": "pass", "reason": None, "latency": first.latency, "input_tokens": 400,
        "output_tokens": 20, "attempt": 1,
    }
    assert model.attempts == [1]
    assert model.model.requests[0]["format"] == SCHEMA
    assert (after["rejects"], after["forced_passes"], after["round"]) == (0, 0, 1)
    assert after["rejected"] == []


def test_the_schema_requires_a_verdict_and_a_reason_that_may_be_empty() -> None:
    assert SCHEMA["required"] == ["verdict", "reason"]
    assert SCHEMA["properties"]["verdict"] == {"type": "string", "enum": ["pass", "fail"]}
    assert SCHEMA["properties"]["reason"] == {"type": "string"}


def test_a_fail_then_a_pass_routes_to_b_once_then_to_e(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = Challenger(monkeypatch, ("fail", ENGLISH), ("pass", ""))
    rejected = model.d(described(round_one, FIRST, attempt=3))

    assert route_after_d(rejected) == "B"
    assert rejected["verdict"] is not None
    assert (rejected["verdict"]["verdict"], rejected["verdict"]["reason"]) == ("fail", ENGLISH)
    assert rejected["rejected"] == [{"round": 1, "description": FIRST, "reason": ENGLISH}]
    assert (rejected["rejects"], rejected["round"], rejected["forced_passes"]) == (1, 1, 0)
    assert rejected["describer_send_backs"] == 0
    assert rejected["guesser_input"] is None
    assert rejected["earlier_texts"] == []
    assert rejected["reason_reasks"] == 0

    passed = model.d(described(rejected, SECOND))
    assert route_after_d(passed) == "E"
    assert passed["guesser_input"] is not None
    assert passed["guesser_input"]["text"] == SECOND
    assert passed["earlier_texts"] == [{"round": 1, "kind": "description", "text": SECOND}]
    assert passed["rejected"] == [{"round": 1, "description": FIRST, "reason": ENGLISH}]
    assert (passed["rejects"], passed["round"]) == (1, 1)
    assert model.attempts == [1, 1]


def test_three_fails_reach_e_as_a_forced_pass(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    reasons = [f"Reason {n} names a detail that also fits a fried oyster omelette." for n in "123"]
    model = Challenger(monkeypatch, *(("fail", r) for r in reasons))
    state = round_one
    routes = []
    for text in (FIRST, SECOND, THIRD):
        state = model.d(described(state, text))
        routes.append(route_after_d(state))

    assert routes == ["B", "B", "E"]
    assert (state["forced_passes"], state["rejects"], state["round"]) == (1, 2, 1)
    assert state["guesser_input"] is not None
    assert state["guesser_input"]["text"] == THIRD
    assert state["rejected"] == [
        {"round": 1, "description": FIRST, "reason": reasons[0]},
        {"round": 1, "description": SECOND, "reason": reasons[1]},
    ]
    assert state["earlier_texts"] == [{"round": 1, "kind": "description", "text": THIRD}]
    assert state["verdict"] is not None
    assert (state["verdict"]["verdict"], state["verdict"]["reason"]) == ("fail", reasons[2])
    assert model.attempts == [1, 1, 1]


def test_rejects_restart_with_the_next_round(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = Challenger(monkeypatch, ("fail", ENGLISH), ("fail", ENGLISH), ("fail", ENGLISH),
                       ("fail", ENGLISH))
    state = round_one
    for text in (FIRST, SECOND, THIRD):
        state = model.d(described(state, text))
    state = model.d(described(node_g(state), FIRST))

    assert route_after_d(state) == "B"
    assert (state["round"], state["rejects"], state["forced_passes"]) == (2, 1, 1)
    assert state["rejected"][-1] == {"round": 2, "description": FIRST, "reason": ENGLISH}


def test_a_reject_routes_to_b_whatever_earlier_texts_holds(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale: State = {
        **described(round_one, SECOND),
        "earlier_texts": [{"round": 1, "kind": "answer", "text": "A stale entry of this round."}],
    }
    model = Challenger(monkeypatch, ("fail", ENGLISH))
    after = model.d(stale)

    assert after["d_route"] == "B"
    assert route_after_d(after) == "B"


def test_the_route_before_d_has_run_raises(round_one: State) -> None:
    assert round_one["d_route"] is None
    with pytest.raises(ValueError, match="before D wrote a route"):
        route_after_d(round_one)


def assert_one_reask(model: Challenger, after: State) -> None:
    """Two calls: the re-ask follows the first reply and carries attempt 2 [R26]; the verdict
    row keeps the first call's latency, tokens, and attempt."""
    assert model.attempts == [1, 2]
    first_messages, reask_messages = model.model.sent
    (prompt,) = first_messages
    assert reask_messages[0] == prompt
    assert isinstance(reask_messages[1], AIMessage)
    assert json.loads(reask_messages[1].text) == model.replies[0].output
    assert reask_messages[2] == HumanMessage(SECTIONS["re-ask [R40]"])
    assert len(reask_messages) == 3
    assert [r["format"] for r in model.model.requests] == [SCHEMA, SCHEMA]
    first = model.replies[0]
    assert after["verdict"] is not None
    assert (after["verdict"]["latency"], after["verdict"]["input_tokens"],
            after["verdict"]["output_tokens"], after["verdict"]["attempt"]) == (
        first.latency, 400, 20, 1)
    assert after["reason_reasks"] == 1


@pytest.mark.parametrize("bad", [CHINESE, "", "  "])
def test_a_fail_with_a_bad_reason_then_an_english_one_keeps_the_english_reason(
    round_one: State, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    model = Challenger(monkeypatch, ("fail", bad), ("fail", ENGLISH))
    after = model.d(described(round_one, FIRST))

    assert_one_reask(model, after)
    assert after["verdict"] is not None
    assert (after["verdict"]["verdict"], after["verdict"]["reason"]) == ("fail", ENGLISH)
    assert after["rejected"] == [{"round": 1, "description": FIRST, "reason": ENGLISH}]
    assert route_after_d(after) == "B"


@pytest.mark.parametrize(("bad", "again"), [(CHINESE, CHINESE), ("", ""), ("", CHINESE),
                                             (CHINESE, "")])
def test_a_bad_reason_twice_gives_the_fixed_message_with_the_fail_kept(
    round_one: State, monkeypatch: pytest.MonkeyPatch, bad: str, again: str
) -> None:
    model = Challenger(monkeypatch, ("fail", bad), ("fail", again))
    after = model.d(described(round_one, FIRST))

    assert_one_reask(model, after)
    assert after["verdict"] is not None
    assert (after["verdict"]["verdict"], after["verdict"]["reason"]) == ("fail", FIXED)
    assert after["rejected"] == [{"round": 1, "description": FIRST, "reason": FIXED}]
    assert route_after_d(after) == "B"


def test_a_reask_that_answers_pass_leaves_the_first_calls_fail(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = Challenger(monkeypatch, ("fail", CHINESE), ("pass", ENGLISH))
    after = model.d(described(round_one, FIRST))

    assert_one_reask(model, after)
    assert after["verdict"] is not None
    assert (after["verdict"]["verdict"], after["verdict"]["reason"]) == ("fail", ENGLISH)
    assert route_after_d(after) == "B"
    assert after["rejects"] == 1
    assert after["guesser_input"] is None


@pytest.mark.parametrize("given", [CHINESE, ENGLISH, ""])
def test_a_pass_drops_its_reason_after_one_call(
    round_one: State, monkeypatch: pytest.MonkeyPatch, given: str
) -> None:
    model = Challenger(monkeypatch, ("pass", given))
    after = model.d(described(round_one, FIRST))

    assert model.attempts == [1]
    assert after["verdict"] is not None
    assert (after["verdict"]["verdict"], after["verdict"]["reason"]) == ("pass", None)
    assert after["reason_reasks"] == 0
    assert route_after_d(after) == "E"


def test_an_english_fail_reason_is_kept_without_a_reask(
    round_one: State, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = Challenger(monkeypatch, ("fail", ENGLISH))
    after = model.d({**described(round_one, FIRST), "reason_reasks": 1})

    assert model.attempts == [1]
    assert after["reason_reasks"] == 0
    assert after["verdict"] is not None
    assert after["verdict"]["reason"] == ENGLISH


def test_d_without_a_description_raises(round_one: State) -> None:
    with pytest.raises(ValueError, match="no description"):
        node_d(round_one, SETTINGS, lambda settings: pytest.fail("no call expected"))
