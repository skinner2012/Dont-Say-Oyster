"""Whole V2 games through the `play-game` command on the committed card 烤蚵仔 and the committed
corpus, with one scripted model per role injected through `main(argv, client_for=...)` (T13
Acceptance); the recursion limit and its arithmetic; the settings the command builds; the
errors; `--help`."""

import json
import logging
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from dont_say_oyster import play
from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, Card, load_cards
from dont_say_oyster.challenger import REJECT_LIMIT
from dont_say_oyster.corpus import CorpusEntry, load_corpus
from dont_say_oyster.graph import (
    RECURSION_LIMIT,
    WORST_CASE_STEPS,
    RoleSettings,
    build_graph,
    play_game,
)
from dont_say_oyster.guesser import INVALID_QUESTION_LIMIT
from dont_say_oyster.llm import ModelSettings
from dont_say_oyster.play import (
    CORPUS_PATH,
    KEEP_ALIVE_CHALLENGER,
    KEEP_ALIVE_RESIDENT,
    main,
    role_settings,
)
from dont_say_oyster.program_nodes import SEND_BACKS, node_a
from dont_say_oyster.state import PROGRAM_ONLY, ROUNDS, State
from tests.test_llm import Scripted, reply, scripted

CARD_ID = "card-5ed17f8f"  # 烤蚵仔
CLEAN = (
    "A street-stall snack of shellfish cooked over hot coals until the edges curl. "
    "It is topped with garlic, chili, and a splash of soy sauce paste."
)
CLEAN_2 = "Plump shellfish cooked over a flame until they pop open, served with a squeeze of lime."
CLEAN_3 = "Opened over heat and eaten hot from the half casing with garlic and chili on top."
CHINESE = "A night-market snack (夜市) of shellfish cooked over hot coals until the edges curl."
FORBIDDEN = "It is a grilled oyster from a night-market stall."  # oyster and grilled [R21]
ANSWER = "Yes, it is eaten hot, straight off the heat."
FAIL_REASON = "The detail of a batter coating also fits a fried oyster fritter."
INVALID = "Is it like an oyster omelet?"  # 蚵仔煎 is a distractor; its English names include it
VALID = "Is it eaten with a dipping sauce?"
WRONG = "蚵仔煎"
RIGHT = "烤牡蠣"  # an alias
ROLES = ("Describer", "Challenger", "Guesser")


# Scripted replies, one builder per kind of call.


def text(content: str) -> AIMessage:
    """A Describer reply."""
    return reply(content, 900, 60)


def verdict(value: str, reason: str = "") -> AIMessage:
    """A Challenger reply."""
    return reply(json.dumps({"verdict": value, "reason": reason}), 400, 20)


def no_tool_calls() -> AIMessage:
    """A Guesser tool-loop reply that makes no tool call, so the loop ends."""
    return reply("", 300, 20)


def guess(content: str) -> AIMessage:
    return reply(
        json.dumps({"kind": "guess", "text": content, "confidence": 0.8}, ensure_ascii=False),
        400,
        15,
    )


def question(content: str) -> AIMessage:
    return reply(json.dumps({"kind": "question", "text": content, "confidence": 0.5}), 400, 15)


def guesser_turn(*structured: AIMessage) -> list[AIMessage]:
    """One visit of E: the tool-loop reply, then the structured replies of its tries."""
    return [no_tool_calls(), *structured]


class Models:
    """One scripted model per role, handed out by `settings.role`; keeps the settings asked
    for."""

    def __init__(
        self,
        describer: Sequence[AIMessage] = (),
        challenger: Sequence[AIMessage] = (),
        guesser: Sequence[AIMessage] = (),
        challenger_model: Scripted | None = None,
    ) -> None:
        self.models: dict[str, Scripted] = {
            "Describer": scripted(*describer),
            "Challenger": challenger_model or scripted(*challenger),
            "Guesser": scripted(*guesser),
        }
        self.settings: dict[str, list[ModelSettings]] = {role: [] for role in ROLES}

    def __call__(self, settings: ModelSettings) -> Scripted:
        self.settings[settings.role].append(settings)
        return self.models[settings.role]

    def calls(self, role: str) -> int:
        """How many requests the role's model received."""
        return len(self.models[role].requests)


def run(
    tmp_path: Path, models: Models, *extra: str, card_id: str = CARD_ID
) -> tuple[int, Path]:
    """Run the command on `card_id` with `models`; return the exit code and the output path."""
    output = tmp_path / "game.json"
    code = main([card_id, str(output), *extra], client_for=models)
    return code, output


def final_state(output: Path) -> State:
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data  # type: ignore[return-value]


@pytest.fixture(scope="module")
def corpus() -> list[CorpusEntry]:
    return load_corpus(CORPUS_PATH)


@pytest.fixture(scope="module")
def cards(corpus: list[CorpusEntry]) -> list[Card]:
    return load_cards(CARDS_PATH, corpus)


# Whole games.


def test_a_right_guess_in_round_1_wins_and_writes_the_final_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, output = run(tmp_path, models)
    assert code == 0
    state = final_state(output)
    assert (state["result"], state["matched_name"], state["round"]) == ("right guess", RIGHT, 1)
    assert state["card_id"] == CARD_ID and state["names"][0] == "烤蚵仔"
    assert state["description"] is not None and state["description"]["description"] == CLEAN
    assert state["guesser_output"] is not None and state["guesser_output"]["text"] == RIGHT
    assert state["earlier_texts"] == [{"round": 1, "kind": "description", "text": CLEAN}]
    assert state["earlier_guesses"] == [
        {"round": 1, "kind": "guess", "text": RIGHT, "confidence": 0.8}
    ]
    assert PROGRAM_ONLY <= state.keys()
    line = capsys.readouterr().out.strip()
    assert line == "Guesser wins (right guess): round 1, questions 0, rejects 0, forced passes 0"
    assert [models.calls(role) for role in ROLES] == [1, 1, 2]


def test_a_game_through_send_back_reject_question_answer_and_wrong_guess(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        # Round 1: Chinese, sent back; clean, rejected; clean, passed. Round 2: the answer.
        # Round 3: a description.
        describer=[text(CHINESE), text(CLEAN), text(CLEAN_2), text(ANSWER), text(CLEAN_3)],
        challenger=[verdict("fail", FAIL_REASON), verdict("pass"), verdict("pass")],
        guesser=[
            *guesser_turn(question(VALID)),  # round 1
            *guesser_turn(guess(WRONG)),  # round 2, on the answer
            *guesser_turn(guess(RIGHT)),  # round 3
        ],
    )
    code, output = run(tmp_path, models)
    assert code == 0
    state = final_state(output)
    assert state["result"] == "right guess"
    assert (state["round"], state["questions"], state["forced_passes"]) == (3, 1, 0)
    assert state["rejects"] == 0  # this round's [R25]
    assert state["rejected"] == [{"round": 1, "description": CLEAN, "reason": FAIL_REASON}]
    assert state["earlier_texts"] == [
        {"round": 1, "kind": "description", "text": CLEAN_2},
        {"round": 2, "kind": "answer", "text": ANSWER},
        {"round": 3, "kind": "description", "text": CLEAN_3},
    ]
    assert [(g["round"], g["kind"], g["text"]) for g in state["earlier_guesses"]] == [
        (1, "question", VALID),
        (2, "guess", WRONG),
        (3, "guess", RIGHT),
    ]
    assert state["answer"] is not None and state["answer"]["answer"] == ANSWER
    # The Challenger judged the two descriptions of round 1 and the one of round 3, never the
    # answer [R12].
    assert [models.calls(role) for role in ROLES] == [5, 3, 6]
    assert capsys.readouterr().out.strip() == (
        "Guesser wins (right guess): round 3, questions 1, rejects 1, forced passes 0"
    )


def test_a_forbidden_word_in_round_2_is_a_describer_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN), text(FORBIDDEN)],
        challenger=[verdict("pass")],
        guesser=guesser_turn(guess(WRONG)),
    )
    code, output = run(tmp_path, models)
    assert code == 0
    state = final_state(output)
    assert (state["result"], state["violation"], state["round"]) == (
        "Describer violation",
        "Describer",
        2,
    )
    assert capsys.readouterr().out.startswith("Guesser wins (Describer violation): round 2")
    assert [models.calls(role) for role in ROLES] == [2, 1, 2]


def test_three_invalid_questions_are_a_guesser_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)],
        challenger=[verdict("pass")],
        guesser=guesser_turn(*[question(INVALID)] * INVALID_QUESTION_LIMIT),
    )
    code, output = run(tmp_path, models)
    assert code == 0
    state = final_state(output)
    assert (state["result"], state["violation"], state["questions"]) == (
        "Guesser violation",
        "Guesser",
        0,
    )
    assert state["earlier_guesses"] == []
    assert capsys.readouterr().out.startswith("Guesser loses (Guesser violation): round 1")
    assert [models.calls(role) for role in ROLES] == [1, 1, 1 + INVALID_QUESTION_LIMIT]


def test_ten_wrong_guesses_lose_in_round_10_with_no_eleventh_round(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)] * ROUNDS,
        challenger=[verdict("pass")] * ROUNDS,
        guesser=[m for _ in range(ROUNDS) for m in guesser_turn(guess(WRONG))],
    )
    code, output = run(tmp_path, models)
    assert code == 0
    state = final_state(output)
    assert (state["result"], state["round"], state["guess_only"]) == (
        "wrong guess in round 10",
        ROUNDS,
        True,
    )
    assert [g["round"] for g in state["earlier_guesses"]] == list(range(1, ROUNDS + 1))
    assert [t["round"] for t in state["earlier_texts"]] == list(range(1, ROUNDS + 1))
    # Every scripted reply was used and none was asked for beyond them.
    assert [models.calls(role) for role in ROLES] == [ROUNDS, ROUNDS, 2 * ROUNDS]
    assert capsys.readouterr().out.strip() == (
        "Guesser loses (wrong guess in round 10): round 10, questions 0, rejects 0, "
        "forced passes 0"
    )


def worst_case() -> Models:
    """The scripted worst case: in each of ten rounds, three descriptions each sent back twice,
    two rejects then a forced pass, and a wrong guess, preceded in rounds 1–9 by two invalid
    questions."""
    descriptions_per_round = REJECT_LIMIT + 1
    describer = [
        m
        for _ in range(ROUNDS)
        for _ in range(descriptions_per_round)
        for m in [*[text(CHINESE)] * SEND_BACKS, text(CLEAN)]
    ]
    challenger = [verdict("fail", FAIL_REASON)] * (ROUNDS * descriptions_per_round)
    guesser = [
        m
        for round_ in range(1, ROUNDS + 1)
        for m in guesser_turn(
            *([question(INVALID)] * (INVALID_QUESTION_LIMIT - 1) if round_ < ROUNDS else []),
            guess(WRONG),
        )
    ]
    return Models(describer=describer, challenger=challenger, guesser=guesser)


def assert_worst_case_outcome(state: State) -> None:
    assert (state["result"], state["round"]) == ("wrong guess in round 10", ROUNDS)
    assert state["forced_passes"] == ROUNDS
    assert len(state["rejected"]) == ROUNDS * REJECT_LIMIT
    assert state["rejects"] == REJECT_LIMIT
    assert state["questions"] == 0
    assert len(state["earlier_guesses"]) == ROUNDS


def test_the_worst_case_game_reaches_f_without_hitting_the_recursion_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configs: list[Any] = []
    real_invoke = CompiledStateGraph.invoke

    def spy(self: Any, input: Any, config: Any = None, **kwargs: Any) -> Any:
        configs.append(config)
        return real_invoke(self, input, config, **kwargs)

    monkeypatch.setattr(CompiledStateGraph, "invoke", spy)
    models = worst_case()
    code, output = run(tmp_path, models)
    assert code == 0
    assert_worst_case_outcome(final_state(output))
    assert configs == [{"recursion_limit": RECURSION_LIMIT}]
    assert [models.calls(role) for role in ROLES] == [
        ROUNDS * (REJECT_LIMIT + 1) * (SEND_BACKS + 1),
        ROUNDS * (REJECT_LIMIT + 1),
        ROUNDS * (1 + INVALID_QUESTION_LIMIT) - (INVALID_QUESTION_LIMIT - 1),
    ]
    assert capsys.readouterr().out.strip() == (
        "Guesser loses (wrong guess in round 10): round 10, questions 0, rejects 20, "
        "forced passes 10"
    )


def test_the_worst_case_arithmetic_is_exact(cards: list[Card], corpus: list[CorpusEntry]) -> None:
    """The worst-case game makes exactly WORST_CASE_STEPS node visits: LangGraph needs the
    limit above the visit count, so the limit at the count fails and one above passes."""
    assert RECURSION_LIMIT > WORST_CASE_STEPS
    assert WORST_CASE_STEPS == 240
    settings = role_settings(play.build_parser().parse_args([CARD_ID, "out.json"]))
    (card,) = [c for c in cards if c.card_id == CARD_ID]
    with pytest.raises(GraphRecursionError):
        build_graph(settings, corpus, worst_case()).invoke(
            node_a(CARD_ID, [card]), RunnableConfig(recursion_limit=WORST_CASE_STEPS)
        )
    state = build_graph(settings, corpus, worst_case()).invoke(
        node_a(CARD_ID, [card]), RunnableConfig(recursion_limit=WORST_CASE_STEPS + 1)
    )
    assert_worst_case_outcome(cast(State, state))


# Errors.


def test_a_challenger_connection_error_in_round_2_exits_non_zero_without_an_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def replies() -> Iterator[AIMessage]:
        yield verdict("pass")
        raise httpx.ConnectError("[Errno 61] Connection refused")

    models = Models(
        describer=[text(CLEAN), text(CLEAN_2)],
        challenger_model=Scripted(messages=replies(), requests=[]),
        guesser=[*guesser_turn(guess(WRONG)), *guesser_turn(guess(RIGHT))],
    )
    code, output = run(tmp_path, models)
    assert code != 0
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Challenger" in captured.err and "Connection refused" in captured.err
    assert [models.calls(role) for role in ROLES] == [2, 2, 2]


def test_an_unknown_card_id_exits_non_zero_before_any_model_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, output = run(tmp_path, models, card_id="card-00000000")
    assert code != 0
    assert not output.exists()
    assert "card-00000000" in capsys.readouterr().err
    assert [models.calls(role) for role in ROLES] == [0, 0, 0]
    assert models.settings == {role: [] for role in ROLES}


def test_node_a_raises_on_an_unknown_card_id_before_the_graph_runs(
    cards: list[Card], corpus: list[CorpusEntry]
) -> None:
    settings = role_settings(play.build_parser().parse_args([CARD_ID, "out.json"]))
    models = Models()
    with pytest.raises(KeyError, match="card-00000000"):
        play_game("card-00000000", cards, corpus, settings, models)
    assert [models.calls(role) for role in ROLES] == [0, 0, 0]


def test_a_missing_cards_file_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run(tmp_path, Models(), "--cards", str(tmp_path / "missing.json"))
    assert code != 0 and not output.exists()
    assert "missing.json" in capsys.readouterr().err


# Settings and logging.


def test_the_default_settings_are_the_role_defaults_with_keep_alive_fixed_per_role(
    tmp_path: Path,
) -> None:
    models = Models(
        describer=[text(CLEAN)], challenger=[verdict("pass")], guesser=guesser_turn(guess(RIGHT))
    )
    code, _ = run(tmp_path, models)
    assert code == 0
    assert {role: set(s) for role, s in models.settings.items()} == {
        "Describer": {ModelSettings("Describer", "qwen3.8:27b-q4_K_M", 8192, 0.7, False, "30m")},
        "Challenger": {ModelSettings("Challenger", "gemma4:12b-it-q4_K_M", 4096, 0.7, False, 0)},
        "Guesser": {ModelSettings("Guesser", "gemma4:26b-a4b-it-q4_K_M", 16384, 0.7, False, "30m")},
    }
    assert (KEEP_ALIVE_RESIDENT, KEEP_ALIVE_CHALLENGER) == ("30m", 0)


def test_the_parameters_set_each_roles_model_num_ctx_temperature_and_thinking() -> None:
    args = play.build_parser().parse_args([
        CARD_ID, "out.json",
        "--describer-model", "qwen3.8:9b-q4_K_M", "--describer-num-ctx", "4096",
        "--challenger-model", "gemma4:4b-it-q4_K_M", "--challenger-num-ctx", "2048",
        "--guesser-model", "gemma4:12b-it-q4_K_M", "--guesser-num-ctx", "8192",
        "--temperature", "0.3",
        "--describer-thinking", "on", "--guesser-thinking", "on", "--challenger-thinking", "on",
    ])
    settings = role_settings(args)
    assert settings == RoleSettings(
        describer=ModelSettings("Describer", "qwen3.8:9b-q4_K_M", 4096, 0.3, "medium", "30m"),
        challenger=ModelSettings("Challenger", "gemma4:4b-it-q4_K_M", 2048, 0.3, True, 0),
        guesser=ModelSettings("Guesser", "gemma4:12b-it-q4_K_M", 8192, 0.3, True, "30m"),
    )


def test_thinking_on_is_a_level_for_qwen_and_true_for_gemma() -> None:
    assert play.thinking("qwen3.8:27b-q4_K_M", on=True) == "medium"
    assert play.thinking("gemma4:26b-a4b-it-q4_K_M", on=True) is True
    assert play.thinking("qwen3.8:27b-q4_K_M", on=False) is False
    assert play.thinking("gemma4:12b-it-q4_K_M", on=False) is False


def test_the_command_configures_logging_so_num_ctx_warnings_appear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    configured: list[dict[str, Any]] = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: configured.append(kw))
    models = Models(
        describer=[reply(CLEAN, 7500, 60)],  # over 90% of the Describer's num_ctx 8192
        challenger=[verdict("pass")],
        guesser=guesser_turn(guess(RIGHT)),
    )
    with caplog.at_level(logging.WARNING):
        code, _ = run(tmp_path, models)
    assert code == 0
    assert len(configured) == 1 and configured[0]["level"] == logging.WARNING
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["Describer: prompt tokens 7500 are over 90% of num_ctx 8192"]


# The command's interface.


def test_help_lists_every_parameter(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for parameter in (
        "card_id",
        "output",
        "--cards",
        "--corpus",
        "--describer-model",
        "--describer-num-ctx",
        "--describer-thinking",
        "--challenger-model",
        "--challenger-num-ctx",
        "--challenger-thinking",
        "--guesser-model",
        "--guesser-num-ctx",
        "--guesser-thinking",
        "--temperature",
    ):
        assert parameter in out
    for absent in ("--variant", "--memory", "keep-alive", "keep_alive"):
        assert absent not in out


def test_play_game_is_a_console_script() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["play-game"] == "dont_say_oyster.play:main"
