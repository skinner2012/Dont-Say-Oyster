"""Node H (the memory summary) on scripted structured replies and a State built as a finished
game: what each prompt holds and never holds (Information isolation, Disclosure rule), the two
schemas, the Check rule's redos with the fixed message and the copy-forward on a third failure
(Cross-game memory definition), the files written for the game (Storage), and the calls in
`calls`."""

import json
import re
from dataclasses import fields
from pathlib import Path
from typing import Any, get_args

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatResult

from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, load_cards
from dont_say_oyster.corpus import Attributes, load_corpus
from dont_say_oyster.llm import LLMError, ModelSettings
from dont_say_oyster.matching import has_chinese_characters
from dont_say_oyster.memory import (
    Memory,
    Role,
    advance,
    empty_memory,
    memory_path,
    read_memory,
)
from dont_say_oyster.memory_summary import (
    DESCRIBER_PROMPT_PATH,
    ENTRY_AND_SUMMARY_SCHEMA,
    ENTRY_SCHEMA,
    FIXED_MESSAGE,
    GUESSER_PROMPT_PATH,
    REDO_LIMIT,
    describer_prompt,
    guesser_prompt,
    node_h,
)
from dont_say_oyster.oracle import check_memory
from dont_say_oyster.prompt_sections import sections
from dont_say_oyster.state import (
    CARD_ENGLISH_NAMES,
    CARD_NAMES,
    CHINESE_CHARACTERS,
    PROGRAM_ONLY,
    HFailed,
    HResult,
    Outcome,
    State,
    initial_state,
    winner,
)
from tests.test_llm import Clients, Scripted, reply

DESCRIBER = ModelSettings("Describer", "qwen3.8:27b-q4_K_M", 16384, 0.7, "medium", -1)
GUESSER = ModelSettings("Guesser", "gemma4:26b-a4b-it-q4_K_M", 16384, 0.7, False, -1)
D_SECTIONS = sections(DESCRIBER_PROMPT_PATH)
G_SECTIONS = sections(GUESSER_PROMPT_PATH)
OUTCOMES: tuple[Outcome, ...] = get_args(Outcome)
LAST_ROUND = 7


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


def recording(*outputs: dict[str, str]) -> Recording:
    return Recording(
        messages=iter([reply(json.dumps(o), 900, 60) for o in outputs]),
        requests=[],
        run_metadata=[],
        received=[],
    )


def memory(*games: int, summary: str | None = None, role: str = "D") -> Memory:
    return {
        "entries": [{"game": g, "text": f"S-{role}-memory-entry-{g}"} for g in games],
        "summary": summary,
    }


def finished(
    game: int = 1,
    result: Outcome = "right guess",
    last_guess: str = "S-last-guess",
    describer_memory: Memory | None = None,
    guesser_memory: Memory | None = None,
) -> State:
    """A finished game with a marked value in every row: three rounds, a reject in round 1, a
    question in round 2, a lookup that was searched and one that was not, and a last guess."""
    corpus = load_corpus(REPO_ROOT / "data" / "corpus" / "corpus.json")
    start = initial_state(load_cards(CARDS_PATH, corpus)[0])
    return {
        **start,
        "card_id": "S-card-id",
        "names": ["S-official-name", "S-alias-1", "S-alias-2"],
        "english_names": ["S-english-name-1", "S-english-name-2"],
        "forbidden_words": ["S-forbidden-1", "S-forbidden-2"],
        # Every field, so `card_from_state` can build the card the Check rule reads.
        "attributes": {field.name: ["S-attribute"] for field in fields(Attributes)},
        "distractors": ["S-distractor-1", "S-distractor-2"],
        "guesser_input": {
            "kind": "description", "text": "S-description-3", "latency": 1.0,
            "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "description": {
            "description": "S-description-row", "latency": 1.0, "input_tokens": 1,
            "output_tokens": 1, "attempt": 1,
        },
        "answer": {
            "answer": "S-answer-row", "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
            "attempt": 1,
        },
        "guesser_output": {
            "kind": "guess", "text": last_guess, "confidence": 0.91, "latency": 1.0,
            "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "verdict": {
            "verdict": "pass", "reason": "S-verdict-reason", "latency": 1.0,
            "input_tokens": 1, "output_tokens": 1, "attempt": 1,
        },
        "earlier_texts": [
            {"round": 1, "kind": "description", "text": "S-description-1"},
            {"round": 2, "kind": "answer", "text": "S-answer-2"},
            {"round": LAST_ROUND, "kind": "description", "text": "S-description-3"},
        ],
        "rejected": [
            {"round": 1, "description": "S-rejected-description", "reason": "S-rejected-reason"}
        ],
        "earlier_guesses": [
            {"round": 1, "kind": "guess", "text": "S-first-guess", "confidence": 0.37},
            {"round": 2, "kind": "question", "text": "S-question", "confidence": None},
            {"round": LAST_ROUND, "kind": "guess", "text": last_guess, "confidence": 0.91},
        ],
        "lookups": [
            {
                "round": 1, "call": 1, "name": "search",
                "arguments": {"keywords": ["S-keyword"]},
                "result": {
                    "results": [
                        {"official_name": "S-hit-name-1", "aliases": ["S-hit-alias"],
                         "english_names": ["S-hit-english"], "attributes": {}},
                        {"official_name": "S-hit-name-2", "aliases": [],
                         "english_names": [], "attributes": {}},
                    ],
                    "more_results": True,
                },
                "status": "success", "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
                "attempt": 1,
            },
            {
                "round": LAST_ROUND, "call": 1, "name": "search",
                "arguments": {"dish_type": ["S-filter"]},
                "result": "S-lookup-message",
                "status": "error", "latency": 1.0, "input_tokens": 1, "output_tokens": 1,
                "attempt": 1,
            },
        ],
        "round": LAST_ROUND,
        "rejects": 41,
        "lookup_count": 42,
        "questions": 1,
        "forced_passes": 44,
        "result": result,
        "describer_memory": (
            memory(summary="S-D-memory-summary") if describer_memory is None
            else describer_memory
        ),
        "guesser_memory": (
            memory(summary="S-G-memory-summary", role="G") if guesser_memory is None
            else guesser_memory
        ),
        "game": game,
        "matched_name": "S-matched-name",
        "calls": [{"ordinal": 1, "node": "E", "role": "S-call-role", "round": LAST_ROUND,
                   "attempt": 1, "kind": "structured", "call": None, "latency": 1.0,
                   "input_tokens": 1, "output_tokens": 1}],
        "sent_back": [{"round": 1, "node": "C", "kind": "description", "text": "S-sent-back",
                       "ordinal": 1, "reason": "S-send-back-reason", "replaced": False}],
        "verdicts": [{"round": 1, "verdict": "fail", "reason": "S-verdicts-reason",
                      "ordinal": 1}],
    }


ENTRIES = ({"entry": "D-entry"}, {"entry": "G-entry"})
WITH_SUMMARIES = (
    {"entry": "D-entry", "summary": "D-summary"},
    {"entry": "G-entry", "summary": "G-summary"},
)


def run(
    state: State, directory: Path, *outputs: dict[str, str]
) -> tuple[State, Recording, Clients]:
    model = recording(*outputs)
    clients = Clients(model)
    return node_h(state, DESCRIBER, GUESSER, directory, clients), model, clients


def prompts(model: Recording) -> tuple[str, str]:
    """The Describer's and the Guesser's prompt, in the order H sent them."""
    texts = []
    for messages in model.received:
        (message,) = messages
        assert isinstance(message, HumanMessage)
        texts.append(message.text)
    describer, guesser = texts
    return describer, guesser


def written(entry: str, summary: str | None = None, redos: int = 0,
            failed: list[HFailed] | None = None) -> HResult:
    return {"written": True, "redos": redos, "entry": entry, "summary": summary,
            "failed": failed or []}


def with_card(state: State, names: list[str], english_names: list[str]) -> State:
    return {**state, "names": names, "english_names": english_names}


def send_back(messages: list[BaseMessage], previous: dict[str, str], fixed: str) -> None:
    """`messages` is a redo's request: the prompt, the previous reply as the model's message,
    and the fixed message."""
    prompt, reply, message = messages
    assert isinstance(prompt, HumanMessage)
    assert isinstance(reply, AIMessage)
    assert json.loads(reply.text) == previous
    assert isinstance(message, HumanMessage) and message.text == fixed


# The prompt files


@pytest.mark.parametrize(
    ("texts", "section", "slots"),
    [
        (D_SECTIONS, "prompt", [
            "official_name", "aliases", "english_names", "forbidden_words", "result", "rounds",
            "descriptions_and_answers", "guesses_and_questions", "rejected_descriptions",
            "violating_reply", "memory", "task",
        ]),
        (D_SECTIONS, "task: entry", []),
        (D_SECTIONS, "task: entry and summary", ["fold"]),
        (G_SECTIONS, "prompt", [
            "winner", "rounds", "questions", "descriptions_and_answers",
            "guesses_and_questions", "lookups", "memory", "task",
        ]),
        (G_SECTIONS, "task: entry", []),
        (G_SECTIONS, "task: entry and summary", ["fold"]),
    ],
)
def test_each_section_s_braces_are_exactly_its_slots_each_once(
    texts: dict[str, str], section: str, slots: list[str]
) -> None:
    # The sections are filled with str.format_map, so a stray brace would raise in a game.
    text = texts[section]
    assert re.findall(r"\{[^}]*\}", text) == ["{" + slot + "}" for slot in slots]
    assert text.count("{") == text.count("}") == len(slots)


def test_each_file_has_the_prompt_two_task_sections_and_conventions_naming_every_slot() -> None:
    for texts in (D_SECTIONS, G_SECTIONS):
        assert set(texts) == {
            "prompt", "task: entry", "task: entry and summary", FIXED_MESSAGE, "conventions",
        }
        slots = re.findall(r"\{[^}]*\}", texts["prompt"] + texts["task: entry and summary"])
        assert [s for s in slots if s not in texts["conventions"]] == []


@pytest.mark.parametrize("texts", [D_SECTIONS, G_SECTIONS], ids=["describer", "guesser"])
def test_the_entry_instructions_are_the_same_in_both_task_sections(texts: dict[str, str]) -> None:
    """Only one task section is sent per call, so the paragraph instructing the entry exists
    twice in each file; editing one copy and not the other fails here."""
    entry_only, with_summary = (
        re.split(r"\n\s*\n", texts[name])[0].strip()
        for name in ("task: entry", "task: entry and summary")
    )
    assert entry_only
    assert entry_only == with_summary


def test_the_conventions_never_reach_the_model(tmp_path: Path) -> None:
    for state, outputs in ((finished(1), ENTRIES), (finished(6), WITH_SUMMARIES)):
        _, model, _ = run(state, tmp_path / str(state["game"]), *outputs)
        describer, guesser = prompts(model)
        assert D_SECTIONS["conventions"] not in describer
        assert G_SECTIONS["conventions"] not in guesser
        assert D_SECTIONS[FIXED_MESSAGE] not in describer  # only after a failed check
        assert G_SECTIONS[FIXED_MESSAGE] not in guesser
        for prompt in (describer, guesser):
            assert "=== " not in prompt
            assert re.search(r"\{[a-z_ ]+\}", prompt) is None  # no slot left unfilled


# What the Describer's prompt holds


DESCRIBER_SHOWN = (
    "Official name (Chinese): S-official-name\n",
    "Accepted aliases (Chinese): S-alias-1, S-alias-2\n",
    "English names: S-english-name-1, S-english-name-2\n",
    "Forbidden words: S-forbidden-1, S-forbidden-2\n",
    "Round 1, description: S-description-1",
    "Round 2, answer: S-answer-2",
    f"Round {LAST_ROUND}, description: S-description-3",
    "Round 1, guess: S-first-guess",
    "Round 2, question: S-question",
    f"Round {LAST_ROUND}, guess: S-last-guess",
    "Round 1: S-rejected-description\nReason: S-rejected-reason",
    f"The game lasted {LAST_ROUND} of ten rounds.",
    "Game 1: S-D-memory-entry-1",
    "S-D-memory-summary",
)
DESCRIBER_HIDDEN = (
    "S-card-id", "S-attribute", "S-distractor", "S-verdict-reason", "S-keyword", "S-filter",
    "S-lookup-message", "S-hit", "S-G-memory", "S-matched-name", "S-call-role", "S-sent-back",
    "S-send-back-reason", "S-verdicts-reason",
    "0.37", "0.91", "41", "42", "44",
)
# The two Describer rows; the one `owes` names is shown only after a Describer violation.
VIOLATING = {"description": "S-description-row", "answer": "S-answer-row"}


@pytest.mark.parametrize("result", OUTCOMES)
def test_the_describer_s_prompt_holds_its_items_and_the_game_result(
    result: Outcome, tmp_path: Path
) -> None:
    state = finished(2, result, describer_memory=memory(1, summary="S-D-memory-summary"))
    _, model, _ = run(state, tmp_path, *ENTRIES)
    describer, _ = prompts(model)
    assert describer == describer_prompt(state, D_SECTIONS)
    assert [s for s in DESCRIBER_SHOWN if s not in describer] == []
    assert [s for s in DESCRIBER_HIDDEN if s in describer] == []
    heading = "Your reply that ended the game as a Describer violation"
    if result == "Describer violation":
        assert f"{heading} (it was not delivered to the Guesser):\nS-description-row\n" in describer
        assert "S-answer-row" not in describer
    else:
        assert f"{heading} (it was not delivered to the Guesser):\n(none)\n" in describer
        assert [s for s in VIOLATING.values() if s in describer] == []
    assert f"How this game ended: {result}\n" in describer
    assert describer.count("S-last-guess") == 1  # the last guess is listed once
    assert describer.rstrip().endswith(D_SECTIONS["task: entry"])
    assert set(PROGRAM_ONLY) <= set(state)  # the fixture is a whole State


def test_a_violating_answer_is_shown_as_the_reply_owes_names() -> None:
    state: State = {**finished(2, "Describer violation"), "owes": "answer"}
    prompt = describer_prompt(state, D_SECTIONS)
    assert "(it was not delivered to the Guesser):\nS-answer-row\n" in prompt
    assert "S-description-row" not in prompt


def test_an_empty_memory_and_no_rejects_print_none_in_the_describer_s_prompt() -> None:
    state: State = {**finished(1), "describer_memory": empty_memory(), "rejected": []}
    prompt = describer_prompt(state, D_SECTIONS)
    assert "Descriptions rejected in this game, each with its reason:\n(none)\n" in prompt
    assert "Latest entries:\n(none)\nSummary of older games:\n(none)" in prompt


# What the Guesser's prompt holds


GUESSER_SHOWN = (
    "Who won and who lost: ",
    f"The game lasted {LAST_ROUND} of ten rounds. You asked 1 of your three questions.",
    "Round 1 (description): S-description-1",
    "Round 2 (answer): S-answer-2",
    f"Round {LAST_ROUND} (description): S-description-3",
    "Round 1 (guess, confidence 0.37): S-first-guess",
    "Round 2 (question): S-question",
    f"Round {LAST_ROUND} (guess, confidence 0.91): S-last-guess",
    'Round 1, search {"keywords": ["S-keyword"]}: 2 results, and more matched',
    f'Round {LAST_ROUND}, search {{"dish_type": ["S-filter"]}}: not searched: S-lookup-message',
    "Game 1: S-G-memory-entry-1",
    "S-G-memory-summary",
)
GUESSER_HIDDEN = (
    "S-official-name", "S-alias", "S-english-name", "S-forbidden", "S-distractor",
    "S-card-id", "S-attribute", "S-description-row", "S-answer-row", "S-verdict-reason",
    "S-rejected", "S-hit", "S-D-memory", "S-matched-name", "S-call-role", "S-sent-back",
    "S-send-back-reason", "S-verdicts-reason", "41", "42", "44", *OUTCOMES,
)


@pytest.mark.parametrize("result", OUTCOMES)
def test_the_guesser_s_prompt_holds_its_items_and_the_winner_and_no_card_row_or_result(
    result: Outcome, tmp_path: Path
) -> None:
    state = finished(
        2, result, guesser_memory=memory(1, summary="S-G-memory-summary", role="G")
    )
    _, model, _ = run(state, tmp_path, *ENTRIES)
    _, guesser = prompts(model)
    assert guesser == guesser_prompt(state, G_SECTIONS)
    assert [s for s in GUESSER_SHOWN if s not in guesser] == []
    assert [s for s in GUESSER_HIDDEN if s in guesser] == []
    assert f"Who won and who lost: {winner(result)}\n" in guesser
    assert guesser.count("S-description-3") == 1  # the last round's description is listed once
    assert guesser.rstrip().endswith(G_SECTIONS["task: entry"])


def test_the_official_name_reaches_the_guesser_only_as_its_own_guess(tmp_path: Path) -> None:
    state = finished(1, "right guess", last_guess="S-official-name")
    _, model, _ = run(state, tmp_path, *ENTRIES)
    _, guesser = prompts(model)
    assert guesser.count("S-official-name") == 1
    assert f"Round {LAST_ROUND} (guess, confidence 0.91): S-official-name" in guesser
    other = guesser_prompt(finished(1, "right guess"), G_SECTIONS)
    assert "S-official-name" not in other


def test_no_lookup_prints_none_in_the_guesser_s_prompt() -> None:
    state: State = {**finished(1), "lookups": [], "guesser_memory": empty_memory()}
    prompt = guesser_prompt(state, G_SECTIONS)
    assert "how many results it returned:\n(none)\n" in prompt
    assert "Latest entries:\n(none)\nSummary of older games:\n(none)" in prompt


# The two schemas


def test_a_game_5_state_sends_the_entry_only_schema(tmp_path: Path) -> None:
    state = finished(
        5,
        describer_memory=memory(1, 2, 3, 4),
        guesser_memory=memory(1, 2, 3, 4, role="G"),
    )
    _, model, _ = run(state, tmp_path, *ENTRIES)
    assert model.requests == [{"format": ENTRY_SCHEMA}] * 2
    describer, guesser = prompts(model)
    assert describer.rstrip().endswith(D_SECTIONS["task: entry"])
    assert guesser.rstrip().endswith(G_SECTIONS["task: entry"])
    assert "summary field" not in describer and "summary field" not in guesser


def test_a_game_6_state_sends_the_entry_and_summary_schema_naming_game_1_to_fold(
    tmp_path: Path,
) -> None:
    state = finished(
        6,
        describer_memory=memory(1, 2, 3, 4, 5),
        guesser_memory=memory(1, 2, 3, 4, 5, role="G"),
    )
    _, model, _ = run(state, tmp_path, *WITH_SUMMARIES)
    assert model.requests == [{"format": ENTRY_AND_SUMMARY_SCHEMA}] * 2
    describer, guesser = prompts(model)
    for prompt, texts in ((describer, D_SECTIONS), (guesser, G_SECTIONS)):
        task = texts["task: entry and summary"].format_map({"fold": "Game 1"})
        assert prompt.rstrip().endswith(task)
        assert "pushes the oldest entry out of the latest five: Game 1." in prompt


def test_from_game_6_with_fewer_than_five_entries_the_entry_to_fold_is_none(
    tmp_path: Path,
) -> None:
    # After a copy-forward a role can reach game 6 with four entries; the summary is still asked
    # for by game number.
    state = finished(
        6,
        describer_memory=memory(1, 2, 3, 5),
        guesser_memory=memory(1, 2, 3, 4, 5, role="G"),
    )
    _, model, _ = run(state, tmp_path, *WITH_SUMMARIES)
    assert model.requests == [{"format": ENTRY_AND_SUMMARY_SCHEMA}] * 2
    describer, guesser = prompts(model)
    assert "pushes the oldest entry out of the latest five: (none)." in describer
    assert "pushes the oldest entry out of the latest five: Game 1." in guesser


def test_both_schemas_refuse_an_empty_entry_or_summary() -> None:
    assert ENTRY_SCHEMA["properties"]["entry"]["minLength"] == 1
    for field in ("entry", "summary"):
        assert ENTRY_AND_SUMMARY_SCHEMA["properties"][field]["minLength"] == 1
    assert ENTRY_AND_SUMMARY_SCHEMA["required"] == ["entry", "summary"]


def test_an_empty_entry_from_the_model_is_an_error_and_writes_no_file(tmp_path: Path) -> None:
    with pytest.raises(LLMError):
        run(finished(1), tmp_path, {"entry": ""}, ENTRIES[1])
    assert not tmp_path.joinpath("describer-01.json").exists()


# The files and the State after H


def test_after_game_1_both_files_hold_one_entry_and_no_summary(tmp_path: Path) -> None:
    state = finished(1, describer_memory=empty_memory(), guesser_memory=empty_memory())
    after, _, _ = run(state, tmp_path, *ENTRIES)
    assert memory_path(tmp_path, "describer", 1).exists()
    assert memory_path(tmp_path, "guesser", 1).exists()
    assert read_memory(tmp_path, "describer", 2) == {
        "entries": [{"game": 1, "text": "D-entry"}], "summary": None,
    }
    assert read_memory(tmp_path, "guesser", 2) == {
        "entries": [{"game": 1, "text": "G-entry"}], "summary": None,
    }
    assert after["describer_h"] == written("D-entry")
    assert after["guesser_h"] == written("G-entry")


def test_after_game_6_both_files_hold_games_2_to_6_and_the_new_summary(tmp_path: Path) -> None:
    state = finished(
        6,
        describer_memory=memory(1, 2, 3, 4, 5, summary="S-D-memory-summary"),
        guesser_memory=memory(1, 2, 3, 4, 5, role="G"),
    )
    after, _, _ = run(state, tmp_path, *WITH_SUMMARIES)
    roles: tuple[tuple[Role, str], ...] = (("describer", "D"), ("guesser", "G"))
    for role, tag in roles:
        file = read_memory(tmp_path, role, 7)
        assert [e["game"] for e in file["entries"]] == [2, 3, 4, 5, 6]
        assert file["entries"][:4] == memory(2, 3, 4, 5, role=tag)["entries"]
        assert file["entries"][4] == {"game": 6, "text": f"{tag}-entry"}
        assert file["summary"] == f"{tag}-summary"
    assert after["describer_h"] == written("D-entry", "D-summary")
    assert after["guesser_h"] == written("G-entry", "G-summary")


def test_the_memory_rows_are_left_as_read_at_game_start(tmp_path: Path) -> None:
    state = finished(6, describer_memory=memory(1, 2, 3, 4, 5),
                     guesser_memory=memory(1, 2, 3, 4, 5, role="G"))
    after, _, _ = run(state, tmp_path, *WITH_SUMMARIES)
    assert after["describer_memory"] == state["describer_memory"]
    assert after["guesser_memory"] == state["guesser_memory"]
    assert (state["describer_h"], state["guesser_h"]) == (None, None)
    restored: State = {**after, "calls": state["calls"], "describer_h": None, "guesser_h": None}
    assert restored == state  # H changes nothing else


def test_the_two_calls_are_appended_with_node_h_the_role_the_last_round_and_attempt_1(
    tmp_path: Path,
) -> None:
    state = finished(1)
    after, model, clients = run(state, tmp_path, *ENTRIES)
    assert clients.settings == [DESCRIBER, GUESSER]
    assert after["calls"][:1] == state["calls"]
    new = after["calls"][1:]
    assert [(c["ordinal"], c["node"], c["role"], c["round"], c["attempt"], c["kind"], c["call"])
            for c in new] == [
        (2, "H", "Describer", LAST_ROUND, 1, "structured", None),
        (3, "H", "Guesser", LAST_ROUND, 1, "structured", None),
    ]
    assert [(c["input_tokens"], c["output_tokens"]) for c in new] == [(900, 60)] * 2
    assert [m["round"] for m in model.run_metadata] == [LAST_ROUND] * 2


def test_a_failed_guesser_call_writes_neither_file(tmp_path: Path) -> None:
    with pytest.raises(LLMError):
        run(finished(1), tmp_path, ENTRIES[0], {"text": "not an entry"})
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_a_failed_guesser_advance_writes_neither_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def failing_second(
        memory: Memory, game: int, entry: str, summary: str | None
    ) -> Memory:
        calls.append(game)
        if len(calls) == 2:
            raise ValueError("S-advance-error")
        return advance(memory, game, entry, summary)

    monkeypatch.setattr("dont_say_oyster.memory_summary.advance", failing_second)
    with pytest.raises(ValueError, match="S-advance-error"):
        run(finished(1), tmp_path, *ENTRIES)
    assert len(calls) == 2
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


# The Check rule: redos with the fixed message and the copy-forward on a third failure


NAMED = {"entry": "I guessed S-official-name"}


def test_a_guesser_entry_naming_the_official_name_is_sent_back_twice_then_copied_forward(
    tmp_path: Path,
) -> None:
    state = finished(3)
    after, model, _ = run(state, tmp_path, ENTRIES[0], NAMED, NAMED, NAMED)
    assert len(model.received) == 4
    assert len(model.received[1]) == 1  # the Guesser's first call: the prompt alone
    for messages in model.received[2:]:
        send_back(messages, NAMED, G_SECTIONS[FIXED_MESSAGE])
    new = after["calls"][1:]
    assert [(c["ordinal"], c["node"], c["role"], c["round"], c["attempt"]) for c in new] == [
        (2, "H", "Describer", LAST_ROUND, 1),
        (3, "H", "Guesser", LAST_ROUND, 1),
        (4, "H", "Guesser", LAST_ROUND, 2),
        (5, "H", "Guesser", LAST_ROUND, 3),
    ]
    assert REDO_LIMIT == 2
    assert after["guesser_h"] == {
        "written": False, "redos": 2, "entry": None, "summary": None,
        "failed": [
            {"attempt": a, "ordinal": o, "entry": NAMED["entry"], "summary": None,
             "reasons": [CARD_NAMES]}
            for a, o in ((1, 3), (2, 4), (3, 5))
        ],
    }
    copied = json.loads(memory_path(tmp_path, "guesser", 3).read_text(encoding="utf-8"))
    assert copied == {"role": "guesser", "game": 3, **state["guesser_memory"]}
    assert read_memory(tmp_path, "describer", 4)["entries"][-1] == {"game": 3, "text": "D-entry"}
    assert after["describer_h"] == written("D-entry")


@pytest.mark.parametrize(
    ("entry", "reasons"),
    [
        ("try 烤生蚝 first", [CHINESE_CHARACTERS, CARD_NAMES]),
        ("S-english-name-1s narrowed it", [CARD_ENGLISH_NAMES]),
    ],
    ids=["simplified alias", "english name in the plural"],
)
def test_a_simplified_alias_or_a_plural_english_name_is_caught_by_r22_matching(
    tmp_path: Path, entry: str, reasons: list[str]
) -> None:
    state = with_card(finished(3), ["烤蚵仔", "烤生蠔"], ["S-english-name-1"])
    bad = {"entry": entry}
    after, model, _ = run(state, tmp_path, ENTRIES[0], bad, bad, bad)
    assert len(model.received) == 4
    assert len(model.received[1]) == 1
    for messages in model.received[2:]:
        send_back(messages, bad, G_SECTIONS[FIXED_MESSAGE])
    guesser_calls = [c for c in after["calls"] if c["node"] == "H" and c["role"] == "Guesser"]
    assert [(c["ordinal"], c["attempt"]) for c in guesser_calls] == [(3, 1), (4, 2), (5, 3)]
    result = after["guesser_h"]
    assert result is not None and not result["written"] and result["redos"] == 2
    assert [(f["attempt"], f["ordinal"], f["entry"], f["reasons"]) for f in result["failed"]] == [
        (1, 3, entry, reasons), (2, 4, entry, reasons), (3, 5, entry, reasons),
    ]
    assert read_memory(tmp_path, "guesser", 4) == state["guesser_memory"]


def test_a_game_6_summary_naming_the_answer_is_caught_when_the_entry_is_clean(
    tmp_path: Path,
) -> None:
    state = finished(6, guesser_memory=memory(1, 2, 3, 4, 5, role="G", summary="G-old"))
    bad = {"entry": "clean", "summary": "always start from S-official-name"}
    after, _, _ = run(state, tmp_path, WITH_SUMMARIES[0], bad, bad, bad)
    result = after["guesser_h"]
    assert result is not None and not result["written"]
    assert [(f["entry"], f["summary"], f["reasons"]) for f in result["failed"]] == [
        ("clean", "always start from S-official-name", [CARD_NAMES])
    ] * 3
    copied = read_memory(tmp_path, "guesser", 7)
    assert [e["game"] for e in copied["entries"]] == [1, 2, 3, 4, 5]
    assert copied["summary"] == "G-old"


def test_a_describer_entry_with_chinese_is_sent_back_once_and_its_clean_redo_is_written(
    tmp_path: Path,
) -> None:
    first = {"entry": "蚵仔 fooled it"}
    after, model, _ = run(finished(2), tmp_path, first, {"entry": "D-entry-2"}, ENTRIES[1])
    assert len(model.received) == 3
    send_back(model.received[1], first, D_SECTIONS[FIXED_MESSAGE])
    assert len(model.received[2]) == 1
    assert [(c["ordinal"], c["role"], c["attempt"]) for c in after["calls"][1:]] == [
        (2, "Describer", 1), (3, "Describer", 2), (4, "Guesser", 1),
    ]
    assert after["describer_h"] == written("D-entry-2", redos=1, failed=[
        {"attempt": 1, "ordinal": 2, "entry": "蚵仔 fooled it", "summary": None,
         "reasons": [CHINESE_CHARACTERS]},
    ])
    assert read_memory(tmp_path, "describer", 3)["entries"][-1] == {
        "game": 2, "text": "D-entry-2",
    }
    assert after["guesser_h"] == written("G-entry")


def test_a_describer_entry_naming_the_snack_in_english_is_not_sent_back(tmp_path: Path) -> None:
    # The Write rule allows the Describer's entry card information.
    allowed = {"entry": "S-english-name-1 and S-official-name, S-forbidden-1"}
    after, model, _ = run(finished(1), tmp_path, allowed, ENTRIES[1])
    assert len(model.received) == 2
    assert after["describer_h"] == written(allowed["entry"])


def test_the_fixed_messages_name_no_card_and_hold_no_chinese() -> None:
    # The Guesser's fixed message is sent after a failed check, so under the Disclosure rule it
    # must pass the Guesser's own check against every card in the deck.
    corpus = load_corpus(REPO_ROOT / "data" / "corpus" / "corpus.json")
    cards = load_cards(CARDS_PATH, corpus)
    assert len(cards) == 40
    for card in cards:
        assert not check_memory(G_SECTIONS[FIXED_MESSAGE], card, "guesser").failed
    assert not has_chinese_characters(D_SECTIONS[FIXED_MESSAGE])
    assert not has_chinese_characters(G_SECTIONS[FIXED_MESSAGE])


def test_game_1_failing_three_times_writes_the_empty_memory_as_game_1_s_file(
    tmp_path: Path,
) -> None:
    state = finished(1, describer_memory=empty_memory(), guesser_memory=empty_memory())
    run(state, tmp_path, ENTRIES[0], NAMED, NAMED, NAMED)
    written_file = json.loads(memory_path(tmp_path, "guesser", 1).read_text(encoding="utf-8"))
    assert written_file == {"role": "guesser", "game": 1, "entries": [], "summary": None}
    assert read_memory(tmp_path, "guesser", 2) == empty_memory()


@pytest.mark.parametrize("failing", ["describer", "guesser"])
def test_one_role_s_failure_does_not_affect_the_other_s_file(
    tmp_path: Path, failing: Role
) -> None:
    state = finished(2)
    bad = {"entry": "中文"}
    outputs = (bad, bad, bad, ENTRIES[1]) if failing == "describer" else (ENTRIES[0], bad, bad, bad)
    after, _, _ = run(state, tmp_path, *outputs)
    other: Role = "guesser" if failing == "describer" else "describer"
    assert read_memory(tmp_path, failing, 3) == state[f"{failing}_memory"]  # type: ignore[literal-required]
    advanced = read_memory(tmp_path, other, 3)
    assert advanced["entries"][-1]["game"] == 2
    failing_h = after[f"{failing}_h"]  # type: ignore[literal-required]
    other_h = after[f"{other}_h"]  # type: ignore[literal-required]
    assert failing_h is not None and not failing_h["written"] and failing_h["redos"] == 2
    assert other_h is not None and other_h["written"] and other_h["redos"] == 0


def test_a_model_error_in_a_redo_writes_neither_file(tmp_path: Path) -> None:
    with pytest.raises(LLMError):
        run(finished(1), tmp_path, {"entry": "中文"}, {"text": "not an entry"})
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("blank", [{"entry": "   "}, {"entry": "\n\t"}])
def test_a_blank_entry_is_a_model_error_and_writes_no_file(
    tmp_path: Path, blank: dict[str, str]
) -> None:
    with pytest.raises(LLMError, match="Describer: memory entry is blank"):
        run(finished(1), tmp_path, blank, ENTRIES[1])
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_a_blank_summary_is_a_model_error_and_writes_no_file(tmp_path: Path) -> None:
    state = finished(6, guesser_memory=memory(1, 2, 3, 4, 5, role="G"))
    with pytest.raises(LLMError, match="Guesser: memory summary is blank"):
        run(state, tmp_path, WITH_SUMMARIES[0], {"entry": "clean", "summary": " "})
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []
