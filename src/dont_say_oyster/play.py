"""The one-game command `play-game`: builds the three roles' settings from its parameters, runs
one V2 game on one card through the graph (`graph.play_game`), writes the final State as one
JSON file to the output path, and prints the outcome with the round, question, reject, and
forced pass counts.

Parameters (`SPEC.md` Implementation, Commands, without the variant (M4) and the memory file
(M6)): the card id and the output path; the cards and corpus paths; the model and num_ctx per
role; the temperature; thinking on or off per role. The Ollama endpoint comes from `.env`
through `llm.ollama_client`. keep_alive is not a parameter (`SPEC.md` Implementation, Models):
the Challenger gets 0, so it is unloaded after each call, and the Describer and the Guesser get
one fixed value, `KEEP_ALIVE_RESIDENT`, that keeps them loaded.

Output: until the JSONL record (M4), the output file is the final State as JSON, the
program-only fields (`state.PROGRAM_ONLY`) included, since nothing else records them yet. The
printed line gives the outcome (one of the four F results and who wins) and the counts; the
reject count printed is the whole game's (the length of the earlier rejected descriptions row),
since State's `rejects` counter is scoped to the round [R25]. num_ctx warnings (`llm.py`) go to
stderr through `logging`, configured here. A model error (`LLMError`) stops the game
(`SPEC.md` Recovery, forks, and replay, Model errors): the error goes to stderr, no output file
is written, and the exit code is non-zero. An unknown card id, and an output path that cannot be
written (its parent directory is created if missing), each exit non-zero before any model
call."""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, CardFileError, load_cards
from dont_say_oyster.corpus import CorpusError, load_corpus
from dont_say_oyster.graph import RoleSettings, play_game
from dont_say_oyster.llm import ClientFor, KeepAlive, LLMError, ModelSettings, Thinking
from dont_say_oyster.state import State, winner

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"

# Role defaults: SPEC.md Implementation (Models) with T1's tags and num_ctx readings.
DEFAULT_MODELS = {
    "describer": "qwen3.8:27b-q4_K_M",
    "challenger": "gemma4:12b-it-q4_K_M",
    "guesser": "gemma4:26b-a4b-it-q4_K_M",
}
DEFAULT_NUM_CTX = {"describer": 8192, "challenger": 4096, "guesser": 16384}
DEFAULT_TEMPERATURE = 0.7  # SPEC.md Implementation, Temperature policy
ROLE_NAMES = {"describer": "Describer", "challenger": "Challenger", "guesser": "Guesser"}

# keep_alive (SPEC.md Implementation, Models): the Describer and the Guesser stay resident; the
# Challenger is loaded for each call and unloaded after it. The resident value is -1 (Ollama:
# keep the model loaded until an explicit unload or memory pressure), not a duration, because a
# duration is a guess at the longest idle gap of a resident model: with thinking on, a round's
# Describer calls can idle the Guesser for over half an hour, and a duration shorter than that
# would unload it mid-game and reopen the Q19 eviction question (T13 F2, author, 2026-10-22).
KEEP_ALIVE_RESIDENT: KeepAlive = -1
KEEP_ALIVE_CHALLENGER: KeepAlive = 0


def thinking(model: str, on: bool) -> Thinking:
    """Ollama's `think` value for thinking off or on (T2's record): off is False for every
    model; on is "medium" for Qwen 3.8, which takes levels, and True for the Gemma tags."""
    if not on:
        return False
    return "medium" if model.startswith("qwen3.8") else True


def role_settings(args: argparse.Namespace) -> RoleSettings:
    """The three ModelSettings from the parsed parameters."""

    def settings(role: str, keep_alive: KeepAlive) -> ModelSettings:
        model = getattr(args, f"{role}_model")
        return ModelSettings(
            role=ROLE_NAMES[role],
            model=model,
            num_ctx=getattr(args, f"{role}_num_ctx"),
            temperature=args.temperature,
            thinking=thinking(model, getattr(args, f"{role}_thinking") == "on"),
            keep_alive=keep_alive,
        )

    return RoleSettings(
        describer=settings("describer", KEEP_ALIVE_RESIDENT),
        challenger=settings("challenger", KEEP_ALIVE_CHALLENGER),
        guesser=settings("guesser", KEEP_ALIVE_RESIDENT),
    )


def outcome_line(state: State) -> str:
    """The printed outcome: who wins and the F result, then the counts."""
    result = state["result"]
    if result is None:
        raise ValueError("the game ended with no result")
    return (
        f"{winner(result)} ({result}): round {state['round']}, "
        f"questions {state['questions']}, rejects {len(state['rejected'])}, "
        f"forced passes {state['forced_passes']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="play-game", description="Play one V2 game on one card and write its final State."
    )
    parser.add_argument("card_id", help="the id of the card to play, from the cards file")
    parser.add_argument(
        "output", type=Path, help="path of the JSON file to write the final State to"
    )
    parser.add_argument(
        "--cards",
        type=Path,
        default=CARDS_PATH,
        help=f"path to the cards file (default {CARDS_PATH})",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=CORPUS_PATH,
        help=f"path to the corpus file (default {CORPUS_PATH})",
    )
    for role in ("describer", "challenger", "guesser"):
        name = ROLE_NAMES[role]
        parser.add_argument(
            f"--{role}-model",
            default=DEFAULT_MODELS[role],
            metavar="TAG",
            help=f"the {name}'s Ollama model tag (default {DEFAULT_MODELS[role]})",
        )
        parser.add_argument(
            f"--{role}-num-ctx",
            type=int,
            default=DEFAULT_NUM_CTX[role],
            metavar="N",
            help=f"the {name}'s num_ctx (default {DEFAULT_NUM_CTX[role]})",
        )
        parser.add_argument(
            f"--{role}-thinking",
            choices=("on", "off"),
            default="off",
            help=f"the {name}'s thinking, on or off (default off)",
        )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"the temperature of every role (default {DEFAULT_TEMPERATURE})",
    )
    return parser


def prepare_output(path: Path) -> None:
    """Make the output path writable before the game runs (T13 F1), so a missing directory or an
    unwritable path fails before any model call instead of after a long live run: create the
    parent directory and open the file for append, removing the file again when it did not
    exist, so a game that stops on a model error leaves no output file. Raises OSError when the
    directory or the file cannot be made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    with path.open("a", encoding="utf-8"):
        pass
    if not existed:
        path.unlink()


def main(argv: Sequence[str] | None = None, client_for: ClientFor | None = None) -> int:
    """Run the command; `client_for` replaces the Ollama client factory (tests)."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        corpus = load_corpus(args.corpus)
        cards = load_cards(args.cards, corpus)
    except (CorpusError, CardFileError, OSError) as e:
        print(e, file=sys.stderr)
        return 1
    if not any(card.card_id == args.card_id for card in cards):
        print(f"no card with id {args.card_id} in {args.cards}", file=sys.stderr)
        return 1
    try:
        prepare_output(args.output)
    except OSError as e:
        print(f"cannot write the output file: {e}", file=sys.stderr)
        return 1
    settings = role_settings(args)
    try:
        if client_for is None:
            state = play_game(args.card_id, cards, corpus, settings)
        else:
            state = play_game(args.card_id, cards, corpus, settings, client_for)
    except LLMError as e:
        print(f"the game stopped on a model error: {e}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(outcome_line(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
