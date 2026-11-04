"""The one-game command `play-game`: builds the three roles' settings from its parameters, runs
one game of the given variant on one card through the graph (`graph.play_game`), appends the
game's record (`record.py`) to the output path as one JSON line, and prints the outcome with the
round, question, reject, and forced pass counts.

Parameters (`SPEC.md` Implementation, Commands): the card id and the output path; the variant,
required with no default, so a game's variant is always the caller's and never a silent default
that a manifest could disagree with; the cards and corpus paths; the model and num_ctx per role;
the temperature; thinking on or off per role; and, for V3, where the memory files are and the
game number. The Ollama endpoint comes from `.env` through `llm.ollama_client`. keep_alive is
not a parameter (`SPEC.md` Implementation, Models): the Challenger gets 0, so it is unloaded
after each call, and the Describer and the Guesser get one fixed value, `KEEP_ALIVE_RESIDENT`,
that keeps them loaded.

Cross-game memory (`SPEC.md` Cross-game memory definition, Storage): `--memory-dir` and `--game`
are V3's, required with it and refused with V0–V2 before any model call, so a V2 game never
writes memory and a V3 game never starts from empty memory because an argument was left out.
For V3 the previous game's two files are read (`memory.read_memory`; game 1 reads nothing)
before the output path is checked, so a missing or invalid file fails before any model call too;
the memories and the game number go to node A, and the directory to node H, through
`graph.GameMemory`. After the game, still inside the game's span and before the record is
written, the command measures each role's memory token count (`SPEC.md` Metrics, Per game): the
block the role read at game start, `memory.render` of its memory row, counted by the role's own
model through `llm.ollama_token_count` with the role's settings; two measurements, no entry in
the record's calls. A failure there is a model error like any other: no record, and the game is
rerun as a crash (`SPEC.md` Recovery, forks, and replay), its memory files for this game already
written by H and rewritten by the rerun.

Output: the output file is a JSONL file, and the game appends one line to it, its record
(`SPEC.md` Implementation, Experiment result format; the format is `data/records/schema.json`),
creating the file when it is missing; the final State is not written anywhere, since the record
holds what the game left. The file name is the caller's, and a second game into the same file
adds a second line; a batch is to write one file per game next to its manifest, so the file's
directory names the session (Tracing, below). The printed line gives the outcome (one of the
four F results and who wins) and the counts; the reject count printed is the whole game's (the
length of the earlier rejected descriptions row), since State's `rejects` counter is scoped to
the round [R25]. num_ctx warnings (`llm.py`) go to stderr through `logging`, configured here. A
model error (`LLMError`) stops the game (`SPEC.md` Recovery, forks, and replay, Model errors):
the error goes to stderr, no record is written (an output file that did not exist is not
created), and the exit code is non-zero. An unknown card id, and an output path that cannot be
written (its parent directory is created if missing), each exit non-zero before any model
call.

Tracing (`SPEC.md` Milestones, M3, `tracing.py`): the Langfuse client is built once per game from
`.env` after the checks above; with it, the game runs inside a span named by the card id with the
session id taken from the output file's directory, and the client is flushed in a `finally`, so
a game stopped by a model error still exports the spans it made, the game span ended in error.
No client (`build_client` returns None, after its warning, when a key or the base URL is
missing) means no tracing: the game runs with no span, no handler, and no flush. With wrong
keys the client is built and the exporter logs each rejected export. None of the three stops
the game (author, 2026-10-25)."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from dont_say_oyster import tracing
from dont_say_oyster.cards import CARDS_PATH, REPO_ROOT, CardFileError, load_cards
from dont_say_oyster.corpus import CorpusError, load_corpus
from dont_say_oyster.graph import TOGGLES, VARIANTS, GameMemory, RoleSettings, play_game
from dont_say_oyster.llm import (
    ClientFor,
    KeepAlive,
    LLMError,
    ModelSettings,
    Thinking,
    TokenCounter,
    ollama_client,
    ollama_token_count,
)
from dont_say_oyster.memory import MemoryFileError, Role, read_memory, render
from dont_say_oyster.record import build_record, write_record
from dont_say_oyster.state import State, winner

CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "corpus.json"

# Role defaults: SPEC.md Implementation (Models) with the tags and num_ctx checked on Ollama.
DEFAULT_MODELS = {
    "describer": "qwen3.8:27b-q4_K_M",
    "challenger": "gemma4:12b-it-q4_K_M",
    "guesser": "gemma4:26b-a4b-it-q4_K_M",
}
DEFAULT_NUM_CTX = {"describer": 16384, "challenger": 4096, "guesser": 16384}
DEFAULT_TEMPERATURE = 0.7  # SPEC.md Implementation, Temperature policy
ROLE_NAMES = {"describer": "Describer", "challenger": "Challenger", "guesser": "Guesser"}

# keep_alive (SPEC.md Implementation, Models): the Describer and the Guesser stay resident; the
# Challenger is loaded for each call and unloaded after it. The resident value is -1 (Ollama:
# keep the model loaded until an explicit unload or memory pressure), not a duration, because a
# duration is a guess at the longest idle gap of a resident model: with thinking on, a round's
# Describer calls can idle the Guesser for over half an hour, and a duration shorter than that
# would unload it mid-game and reopen the Q19 eviction question (author, 2026-10-22).
KEEP_ALIVE_RESIDENT: KeepAlive = -1
KEEP_ALIVE_CHALLENGER: KeepAlive = 0


def thinking(model: str, on: bool) -> Thinking:
    """Ollama's `think` value for thinking off or on (checked on Ollama, 2026-10-19): off is False
    for every model; on is "medium" for Qwen 3.8, which takes levels, and True for the Gemma
    tags."""
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
        prog="play-game", description="Play one game on one card and append its record."
    )
    parser.add_argument("card_id", help="the id of the card to play, from the cards file")
    parser.add_argument(
        "output",
        type=Path,
        help="path of the JSONL file to append the game's record to (created when missing)",
    )
    parser.add_argument(
        "--variant",
        choices=VARIANTS,
        required=True,
        help="the ablation variant to play (required)",
    )
    parser.add_argument(
        "--memory-dir",
        type=Path,
        metavar="DIR",
        help="the directory of the cross-game memory files (V3 only, required with it): game N "
        "reads game N-1's two files there and writes its own",
    )
    parser.add_argument(
        "--game",
        type=int,
        metavar="N",
        help="the game's number in the batch, from 1 (V3 only, required with it): game 1 starts "
        "from empty memory",
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
    """Make the output path writable before the game runs, so a missing directory or an
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


def check_memory_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Exit through `parser.error` (usage and the message on stderr, a non-zero code) unless the
    memory parameters match the variant: both given with V3, neither with V0–V2, and the game
    number from 1."""
    memory = TOGGLES[args.variant].memory
    given = args.memory_dir is not None or args.game is not None
    if memory and (args.memory_dir is None or args.game is None):
        parser.error(f"--memory-dir and --game are required with --variant {args.variant}")
    if not memory and given:
        parser.error("--memory-dir and --game apply to --variant V3 only")
    if args.game is not None and args.game < 1:
        parser.error("--game starts at 1")


def memory_token_counts(
    state: State, settings: RoleSettings, count_tokens: TokenCounter
) -> dict[Role, int]:
    """Each role's memory token count (`SPEC.md` Metrics, Per game): the block the role read at
    game start, as the memory rows still hold it after H, counted by the role's own model with
    the role's settings; the Describer's first, then the Guesser's."""
    return {
        "describer": count_tokens(settings.describer, render(state["describer_memory"])),
        "guesser": count_tokens(settings.guesser, render(state["guesser_memory"])),
    }


def main(
    argv: Sequence[str] | None = None,
    client_for: ClientFor | None = None,
    count_tokens: TokenCounter | None = None,
) -> int:
    """Run the command; `client_for` replaces the Ollama client factory and `count_tokens` the
    memory token count (tests)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    check_memory_arguments(parser, args)
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
    toggles = TOGGLES[args.variant]
    memory: GameMemory | None = None
    if toggles.memory:
        try:
            memory = GameMemory(
                args.memory_dir,
                args.game,
                read_memory(args.memory_dir, "describer", args.game),
                read_memory(args.memory_dir, "guesser", args.game),
            )
        except MemoryFileError as e:
            print(f"cannot read the previous game's memory: {e}", file=sys.stderr)
            return 1
    try:
        prepare_output(args.output)
    except OSError as e:
        print(f"cannot write the output file: {e}", file=sys.stderr)
        return 1
    settings = role_settings(args)
    factory = ollama_client if client_for is None else client_for
    counter = ollama_token_count if count_tokens is None else count_tokens
    tracer = tracing.build_client()
    tokens: dict[Role, int] | None = None
    try:
        if tracer is None:
            state = play_game(
                args.card_id, cards, corpus, settings, factory, None, toggles, memory
            )
            if memory is not None:
                tokens = memory_token_counts(state, settings, counter)
        else:
            with tracing.game_span(tracer, args.card_id, tracing.session_id(args.output)):
                state = play_game(
                    args.card_id, cards, corpus, settings, factory, tracer, toggles, memory
                )
                if memory is not None:
                    tokens = memory_token_counts(state, settings, counter)
    except LLMError as e:
        print(f"the game stopped on a model error: {e}", file=sys.stderr)
        return 1
    finally:
        if tracer is not None:
            tracing.flush(tracer)
    write_record(build_record(state, args.variant, settings, tokens), args.output)
    print(outcome_line(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
