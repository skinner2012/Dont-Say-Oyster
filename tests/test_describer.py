"""Node B (Describer) and node C with the [R11] send-back loop, on scripted Describer replies and
the committed card 烤蚵仔 (T9 Acceptance)."""

import re
from typing import Any, Literal

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatResult

from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, Card, load_cards
from dont_say_oyster.corpus import load_corpus
from dont_say_oyster.describer import (
    NONE,
    build_messages,
    build_prompt,
    load_sections,
    node_b,
    parse_sections,
)
from dont_say_oyster.llm import ModelSettings
from dont_say_oyster.program_nodes import node_a, node_c, node_f, node_g, route_after_c
from dont_say_oyster.state import EarlierGuessOrQuestion, GuessOrQuestion, State
from tests.test_llm import Clients, Scripted, reply

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"
CARD_ID = "card-5ed17f8f"
SETTINGS = ModelSettings("describer", "qwen3.8:27b-q4_K_M", 8192, 0.7, False, "30m")
SECTIONS = load_sections()
FIXED = SECTIONS["fixed message [R11]"]
CLEAN = (
    "A street-stall snack of shellfish cooked over hot coals until the edges curl. "
    "It is topped with garlic, chili, and a splash of soy sauce paste. "
    "It is eaten straight from its own casing at night markets."
)
CHINESE = "A night-market snack (夜市) of shellfish cooked over hot coals until the edges curl."
QUESTION = "Is it eaten hot?"


class Recording(Scripted):
    """A scripted chat model that also keeps the messages of each request."""

    received: list[list[BaseMessage]] = []

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


def recording(*texts: str) -> Recording:
    return Recording(messages=iter([reply(t, 900, 60) for t in texts]), requests=[], received=[])


@pytest.fixture(scope="module")
def card() -> Card:
    (found,) = [
        c for c in load_cards(CARDS_PATH, load_corpus(CORPUS_PATH)) if c.card_id == CARD_ID
    ]
    assert found.official_name == "烤蚵仔"
    assert "烤牡蠣" in found.aliases and "oyster" in found.forbidden_words
    assert "蚵仔煎" in found.distractors
    return found


@pytest.fixture
def round_1(card: Card) -> State:
    """Round 1 after G, the Describer asked for a description."""
    return node_g(node_a(CARD_ID, [card]))


def _question(state: State, text: str = QUESTION) -> State:
    """`state` after E: a valid question in the Guesser's output and in the earlier list, a new
    round from G, and the Describer owing an answer."""
    latest: GuessOrQuestion = {
        "kind": "question", "text": text, "confidence": None, "latency": 1.0,
        "input_tokens": 10, "output_tokens": 5, "attempt": 1,
    }
    earlier: EarlierGuessOrQuestion = {
        "round": state["round"], "kind": "question", "text": text, "confidence": None,
    }
    return node_g({
        **state,
        "guesser_output": latest,
        "earlier_guesses": [*state["earlier_guesses"], earlier],
        "owes": "answer",
    })


def _run(state: State, model: Recording) -> tuple[State, Literal["D", "E", "F"], list[int]]:
    """B then C until C routes away from B; the final State, the route, and the attempt
    number of each Describer call."""
    clients = Clients(model)
    attempts: list[int] = []
    while True:
        state = node_b(state, SETTINGS, clients)
        row = state["answer"] if state["owes"] == "answer" else state["description"]
        assert row is not None
        attempts.append(row["attempt"])
        state = node_c(state)
        route = route_after_c(state)
        if route != "B":
            assert clients.settings == [SETTINGS] * len(attempts)
            return state, route, attempts


def _prompt(model: Recording, call: int) -> str:
    """The text of the first message of the `call`-th request (0-based)."""
    message = model.received[call][0]
    assert isinstance(message, HumanMessage)
    return message.text


# The prompt file


def test_the_prompt_section_braces_are_exactly_the_slots_each_once() -> None:
    # build_prompt fills the section with str.format_map, so a stray brace would raise in a game.
    prompt = SECTIONS["prompt"]
    slots = [
        "official_name", "aliases", "english_names", "forbidden_words", "round",
        "earlier_descriptions_and_answers", "earlier_guesses_and_questions",
        "latest_guess_or_question", "latest_verdict", "rejected_descriptions", "task",
    ]
    assert re.findall(r"\{[^}]*\}", prompt) == ["{" + slot + "}" for slot in slots]
    assert prompt.count("{") == prompt.count("}") == len(slots)


def test_a_prompt_file_lacking_a_section_raises_naming_it() -> None:
    with pytest.raises(ValueError, match=r"fixed message \[R11\]"):
        parse_sections("=== prompt ===\nx\n=== task: description ===\ny\n=== task: answer ===\nz")


def test_the_conventions_never_reach_the_model(round_1: State) -> None:
    conventions = SECTIONS["conventions"]
    sent_back: State = {
        **round_1,
        "describer_send_backs": 1,
        "description": {
            "description": CHINESE, "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
            "attempt": 1,
        },
    }
    for messages in (build_messages(round_1, SECTIONS), build_messages(sent_back, SECTIONS)):
        assert all(conventions not in m.text for m in messages)
        assert all("=== " not in m.text for m in messages)


# What the prompt holds


def test_round_1_prints_every_empty_slot_as_none_and_asks_for_a_description(
    round_1: State,
) -> None:
    prompt = build_prompt(round_1, SECTIONS)
    assert "Official name (Chinese): 烤蚵仔\n" in prompt
    assert "Accepted aliases (Chinese): 烤牡蠣, 烤生蠔\n" in prompt
    assert "English names: Grilled oyster\n" in prompt
    assert "Forbidden words: oyster, grilled, shell, charcoal, raw\n" in prompt
    assert "This is round 1 of ten." in prompt
    assert prompt.count(NONE) == 5
    assert prompt.endswith(SECTIONS["task: description"])
    assert SECTIONS["task: answer"] not in prompt


def test_isolation_the_prompt_holds_the_describer_items_and_no_others() -> None:
    state: State = {
        "card_id": "S-card-id",
        "names": ["S-official-name", "S-alias-1", "S-alias-2"],
        "english_names": ["S-english-name"],
        "forbidden_words": ["S-forbidden-1", "S-forbidden-2"],
        "attributes": {"dish_type": ["S-attribute"]},
        "distractors": ["S-distractor"],
        "guesser_input": {
            "kind": "description", "text": "S-guesser-input",
            "latency": 1.0, "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "description": {
            "description": "S-description-row",
            "latency": 1.0, "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "answer": {
            "answer": "S-answer-row",
            "latency": 1.0, "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "guesser_output": {
            "kind": "question", "text": "S-latest-question", "confidence": None,
            "latency": 1.0, "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "verdict": {
            "verdict": "fail", "reason": "S-verdict-reason",
            "latency": 1.0, "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "earlier_texts": [{"round": 1, "kind": "description", "text": "S-earlier-text"}],
        "rejected": [{"round": 1, "description": "S-rejected", "reason": "S-rejected-reason"}],
        "earlier_guesses": [
            {"round": 1, "kind": "guess", "text": "S-earlier-guess", "confidence": 0.3}
        ],
        "lookups": [{"result": "S-lookup"}],
        "round": 7,
        "rejects": 41,
        "lookup_count": 42,
        "questions": 43,
        "forced_passes": 44,
        "result": None,
        "violation": None,
        "matched_name": "S-matched-name",
        "describer_send_backs": 0,
        "invalid_questions": 0,
        "reason_reasks": 0,
        "owes": "description",
        "guess_only": False,
    }
    messages = build_messages(state, SECTIONS)
    assert len(messages) == 1
    prompt = messages[0].text
    shown = (
        "S-official-name", "S-alias-1", "S-alias-2", "S-english-name", "S-forbidden-1",
        "S-forbidden-2", "S-earlier-text", "S-earlier-guess", "S-latest-question",
        "S-verdict-reason", "S-rejected", "S-rejected-reason", "This is round 7 of ten.",
    )
    hidden = (
        "S-card-id", "S-attribute", "S-distractor", "S-guesser-input", "S-description-row",
        "S-answer-row", "S-lookup", "S-matched-name", "0.3", "41", "42", "43", "44",
    )
    assert [s for s in shown if s not in prompt] == []
    assert [s for s in hidden if s in prompt] == []


def test_a_fail_verdict_and_two_rejected_descriptions_are_in_the_prompt(round_1: State) -> None:
    state: State = {
        **round_1,
        "rejects": 2,
        "verdict": {"verdict": "fail", "reason": "It also fits oyster omelette.", "latency": 1.0,
                    "input_tokens": 1, "output_tokens": 1, "attempt": 1},
        "rejected": [
            {"round": 1, "description": "First rejected text.", "reason": "Too vague."},
            {"round": 1, "description": "Second rejected text.",
             "reason": "It also fits oyster omelette."},
        ],
    }
    prompt = build_prompt(state, SECTIONS)
    assert "The verdict on your most recent description:\nfail. Reason: It also fits oyster " \
        "omelette.\n" in prompt
    assert "Round 1: First rejected text.\nReason: Too vague.\n" in prompt
    assert "Round 1: Second rejected text.\nReason: It also fits oyster omelette.\n" in prompt


def test_a_verdict_left_from_an_earlier_round_is_not_shown(round_1: State) -> None:
    state: State = {
        **round_1,
        "rejects": 0,
        "verdict": {"verdict": "fail", "reason": "Stale reason.", "latency": 1.0,
                    "input_tokens": 1, "output_tokens": 1, "attempt": 1},
    }
    prompt = build_prompt(state, SECTIONS)
    assert "Stale reason." not in prompt
    assert "The verdict on your most recent description:\n(none)\n" in prompt


def test_after_a_valid_question_the_prompt_asks_for_an_answer(round_1: State) -> None:
    state = _question({
        **round_1,
        "earlier_texts": [{"round": 1, "kind": "description", "text": CLEAN}],
    })
    prompt = build_prompt(state, SECTIONS)
    assert prompt.endswith(SECTIONS["task: answer"])
    assert SECTIONS["task: description"] not in prompt
    assert f"The Guesser's latest guess or question:\nquestion: {QUESTION}\n" in prompt
    # The latest is not repeated in the earlier list (the prompt file's conventions).
    assert prompt.count(QUESTION) == 1
    assert "The Guesser's earlier guesses and questions in this game (oldest first):\n(none)\n" \
        in prompt
    assert f"Round 1, description: {CLEAN}\n" in prompt
    assert "This is round 2 of ten." in prompt


def test_earlier_guesses_before_the_latest_are_listed(round_1: State) -> None:
    state = _question({
        **round_1,
        "round": 2,
        "earlier_guesses": [{"round": 1, "kind": "guess", "text": "蚵仔煎", "confidence": 0.4}],
    })
    prompt = build_prompt(state, SECTIONS)
    assert "(oldest first):\nRound 1, guess: 蚵仔煎\n" in prompt
    assert prompt.count(QUESTION) == 1


# B and C


def test_chinese_chinese_then_clean_reaches_d_with_the_fixed_message_and_attempts_1_2_3(
    round_1: State,
) -> None:
    model = recording(CHINESE, CHINESE + " Again 夜市.", CLEAN)
    state, route, attempts = _run(round_1, model)
    assert route == "D"
    assert attempts == [1, 2, 3]
    assert state["round"] == 1
    assert state["violation"] is None
    assert state["description"] is not None and state["description"]["description"] == CLEAN
    assert [len(r) for r in model.received] == [1, 3, 3]
    first = model.received[0][0].text
    for call, previous in ((1, CHINESE), (2, CHINESE + " Again 夜市.")):
        prompt, sent, fixed = model.received[call]
        assert isinstance(prompt, HumanMessage) and prompt.text == first
        assert isinstance(sent, AIMessage) and sent.text == previous
        assert isinstance(fixed, HumanMessage) and fixed.text == FIXED


def test_after_a_reject_the_new_description_gets_its_own_two_send_backs(round_1: State) -> None:
    state, route, attempts = _run(round_1, recording(CHINESE, CHINESE, CLEAN))
    assert (route, attempts, state["describer_send_backs"]) == ("D", [1, 2, 3], 2)
    # D's fail, as T10 leaves the State: the reject counted, the [R11] count zeroed.
    rejected: State = {
        **state,
        "rejects": 1,
        "describer_send_backs": 0,
        "verdict": {"verdict": "fail", "reason": "It also fits oyster omelette.",
                    "latency": 1.0, "input_tokens": 1, "output_tokens": 1, "attempt": 1},
        "rejected": [{"round": 1, "description": CLEAN, "reason": "It also fits oyster omelette."}],
    }
    model = recording(CHINESE, CHINESE, CLEAN)
    state, route, attempts = _run(rejected, model)
    assert (route, attempts, state["round"]) == ("D", [1, 2, 3], 1)
    assert "fail. Reason: It also fits oyster omelette." in _prompt(model, 0)


def test_an_alias_is_a_violation_after_one_call_with_no_send_back(round_1: State) -> None:
    model = recording("Some call it 烤牡蠣 at the stalls.")
    state, route, attempts = _run(round_1, model)
    assert (route, attempts, len(model.received)) == ("F", [1], 1)
    assert state["violation"] == "Describer" and state["describer_send_backs"] == 0
    assert node_f(state)["result"] == "Describer violation"


def test_a_distractor_name_is_sent_back(round_1: State) -> None:
    state = node_b(round_1, SETTINGS, Clients(recording("It is not 蚵仔煎 at all.")))
    state = node_c(state)
    assert route_after_c(state) == "B"
    assert (state["describer_send_backs"], state["violation"]) == (1, None)


def test_chinese_three_times_is_a_violation(round_1: State) -> None:
    model = recording(CHINESE, CHINESE, CHINESE)
    state, route, attempts = _run(round_1, model)
    assert (route, attempts, state["violation"]) == ("F", [1, 2, 3], "Describer")
    assert node_f(state)["result"] == "Describer violation"


def test_a_forbidden_word_plural_is_a_violation(round_1: State) -> None:
    model = recording("Plump oysters are cooked on a rack until they open.")
    state, route, attempts = _run(round_1, model)
    assert (route, attempts, state["violation"]) == ("F", [1], "Describer")


def test_a_name_with_chinese_is_a_violation_not_a_send_back(round_1: State) -> None:
    model = recording("Plump oysters (夜市) are cooked on a rack.")
    state, route, attempts = _run(round_1, model)
    assert (route, attempts, state["describer_send_backs"]) == ("F", [1], 0)


def test_a_clean_answer_reaches_e_filling_the_guesser_row_and_the_earlier_list(
    round_1: State,
) -> None:
    asked = _question({
        **round_1,
        "earlier_texts": [{"round": 1, "kind": "description", "text": CLEAN}],
    })
    model = recording("Yes, it is served sizzling hot.")
    state, route, attempts = _run(asked, model)
    assert (route, attempts) == ("E", [1])
    assert state["answer"] is not None
    assert state["guesser_input"] == {
        "kind": "answer", "text": "Yes, it is served sizzling hot.",
        "latency": state["answer"]["latency"], "input_tokens": 900, "output_tokens": 60,
        "attempt": 1,
    }
    assert state["earlier_texts"] == [
        {"round": 1, "kind": "description", "text": CLEAN},
        {"round": 2, "kind": "answer", "text": "Yes, it is served sizzling hot."},
    ]
    assert state["description"] is None and state["round"] == 2


def test_a_chinese_answer_is_sent_back_and_its_rewrite_reaches_e(round_1: State) -> None:
    model = recording("Yes (熱).", "Yes, it is served hot.")
    state, route, attempts = _run(_question(round_1), model)
    assert (route, attempts) == ("E", [1, 2])
    prompt, sent, fixed = model.received[1]
    assert sent.text == "Yes (熱)." and fixed.text == FIXED
    assert SECTIONS["task: answer"] in prompt.text
    assert state["guesser_input"] is not None and state["guesser_input"]["attempt"] == 2
    assert state["earlier_texts"][-1]["text"] == "Yes, it is served hot."


def test_a_description_does_not_fill_the_guesser_row(round_1: State) -> None:
    state, route, _ = _run(round_1, recording(CLEAN))
    assert route == "D"
    assert (state["guesser_input"], state["earlier_texts"]) == (None, [])


def test_every_reply_carries_latency_token_counts_and_attempt(round_1: State) -> None:
    state = node_b(round_1, SETTINGS, Clients(recording(CLEAN)))
    assert state["description"] == {
        "description": CLEAN, "latency": state["description"]["latency"],  # type: ignore[index]
        "input_tokens": 900, "output_tokens": 60, "attempt": 1,
    }
    assert isinstance(state["description"]["latency"], float)
    answer = node_b(_question(round_1), SETTINGS, Clients(recording("Yes.")))
    assert answer["answer"] is not None
    assert (answer["answer"]["input_tokens"], answer["answer"]["output_tokens"],
            answer["answer"]["attempt"]) == (900, 60, 1)
    assert isinstance(answer["answer"]["latency"], float)


def test_c_without_the_owed_output_raises(round_1: State) -> None:
    with pytest.raises(ValueError, match="no description"):
        node_c(round_1)
