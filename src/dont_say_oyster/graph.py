"""The graph of one game (Full flow of one game): G, B, C, D, E, F, and H as one LangGraph
graph, built from the three toggles of `SPEC.md` Ablation Design (`Toggles`, named here and
nowhere else, and derived from the variant by `TOGGLES`), and `play_game`, which runs it on one
card.

Node A is not a graph node: `node_a` builds the initial State from the card id, the two
cross-game memories, and the game number, and the graph starts at G with that State as its
input, so an unknown card id raises before any model call (A → G is kept). The model nodes B,
D, E, and H take their ModelSettings, the client factory, and (E) the corpus or (H) the memory
files' directory beside State; `build_graph` wraps each in a closure, so every graph node is
`State -> State`. The routers are the node modules' own (`route_after_c`, `route_after_d`,
`route_after_e`, `route_after_f`); they return single-letter node names, which are the node
names here.

Edges with every toggle on (V3): G → B; B → C; C → B (send-back), D (description), E (answer),
or F (violation); D → B (reject) or E (pass or forced pass); E → G (valid question) or F (guess
or violation); F → G (new round) or H (one of the four outcomes); H → the end. With memory off
(V0–V2) there is no H node and no edge to it: F → the end on an outcome (Transitions that differ
between variants), and B and E are built without their memory block. With the Challenger off
(V0–V1) there is no D node and no edge to it: C → E for a description as for an answer, C itself
filling the row the Guesser reads. With corpus lookup off (V0), E makes the structured call
alone, with no tool bound [R47].

The recursion limit is set explicitly from the worst case (see `WORST_CASE_STEPS`), never from
LangGraph's default: langgraph 1.2.16 defaults to 10007 steps, earlier versions to 25, below a
ten-round V2 game.

Tracing (`SPEC.md` Milestones, M3): given a `TracingClient` (`tracing.py`), `play_game` runs node A
inside its span and passes the Langfuse callback handler in the graph's config, so each node visit
is a chain span named by the node's single-letter name, matching the node table in `SPEC.md` Full
flow of one game, under the game span `play.main` opens."""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from dont_say_oyster.cards import Card
from dont_say_oyster.challenger import REJECT_LIMIT, node_d, route_after_d
from dont_say_oyster.corpus import CorpusEntry
from dont_say_oyster.describer import node_b
from dont_say_oyster.guesser import node_e, route_after_e
from dont_say_oyster.llm import ClientFor, ModelSettings, ollama_client
from dont_say_oyster.memory import Memory
from dont_say_oyster.memory_summary import node_h
from dont_say_oyster.program_nodes import (
    SEND_BACKS,
    node_a,
    node_c,
    node_f,
    node_g,
    route_after_c,
    route_after_f,
)
from dont_say_oyster.state import ROUNDS, State
from dont_say_oyster.tracing import TracingClient, callback_handler, node_a_span


@dataclass(frozen=True)
class RoleSettings:
    """The three roles' model call settings."""

    describer: ModelSettings
    challenger: ModelSettings
    guesser: ModelSettings


@dataclass(frozen=True)
class GameMemory:
    """What a game with memory on needs beside the card (Cross-game memory definition, Storage):
    the directory of the memory files, the game number, and the two memories the program read
    at game start (the empty memory for game 1)."""

    directory: Path
    game: int
    describer: Memory
    guesser: Memory


@dataclass(frozen=True)
class Toggles:
    """The toggles that turn nodes off one by one (`SPEC.md` Ablation Design): the Challenger
    (node D), the Guesser's corpus lookup (the tool loop in E), and cross-game memory (the memory
    block in B and E, and node H after F)."""

    challenger: bool
    lookup: bool
    memory: bool


Variant = Literal["V0", "V1", "V2", "V3"]
TOGGLES: dict[Variant, Toggles] = {
    "V0": Toggles(challenger=False, lookup=False, memory=False),
    "V1": Toggles(challenger=False, lookup=True, memory=False),
    "V2": Toggles(challenger=True, lookup=True, memory=False),
    "V3": Toggles(challenger=True, lookup=True, memory=True),
}
VARIANTS: tuple[Variant, ...] = tuple(TOGGLES)
# The default of every function here, V2 being the variant before memory: the main build is V3
# and regresses through V2 (`SPEC.md` Ablation Design).
V2 = TOGGLES["V2"]


# The worst case of one game, counted in node visits (LangGraph counts one step per node visit;
# a conditional edge is not a step; the limit must be above the visit count, so a game of N
# visits needs recursion_limit >= N + 1):
#   per round, with every loop at its maximum:
#     G                                                          1
#     B and C: three descriptions are asked for (two rejects, then the forced pass [R13]),
#       each with two send-backs [R11], so 3 × 3 B/C pairs = 9 pairs, 2 visits each        18
#     D: one verdict per description asked for                   3
#     E: once; the [R17] retries are structured calls inside E, not node visits, and the
#       [R40] re-ask is a call inside D                           1
#     F                                                          1
#                                                               24
#   a round that answers a question is shorter (G, up to three B/C pairs, E, F: 9 visits), so
#   ten description rounds are the worst: 10 × 24 = 240.
#   H, one visit after the last F (V3 only; its redos are calls inside H, not visits)    1
#                                                                                      241
#   With memory off (V0–V2) there is no H visit, so 240. With the Challenger off (V0–V1) a
#   round has no D visit and no reject loop, so at most one description is asked for (G, up to
#   three B/C pairs, E, F: 9 visits); the limit below is the V3 worst case and so an upper
#   bound for V0–V2 too.
DESCRIPTIONS_PER_ROUND = REJECT_LIMIT + 1
B_C_VISITS_PER_DESCRIPTION = (SEND_BACKS + 1) * 2
STEPS_PER_ROUND = (
    1  # G
    + DESCRIPTIONS_PER_ROUND * B_C_VISITS_PER_DESCRIPTION  # 3 × 6 = 18
    + DESCRIPTIONS_PER_ROUND  # D
    + 1  # E
    + 1  # F
)
WORST_CASE_STEPS_WITHOUT_MEMORY = ROUNDS * STEPS_PER_ROUND  # 10 × 24 = 240 (V0–V2)
WORST_CASE_STEPS = WORST_CASE_STEPS_WITHOUT_MEMORY + 1  # + H = 241 (V3)
RECURSION_LIMIT = WORST_CASE_STEPS + 60  # the required +1 and a margin; 301


def _memory_directory(toggles: Toggles, memory_dir: Path | None) -> Path | None:
    """`memory_dir` after checking it against the memory toggle, so the two agree: a game with
    memory on has nowhere to write without a directory, and a game with memory off must never
    write memory (Cross-game memory definition, Storage). Raises ValueError when they
    disagree."""
    if toggles.memory and memory_dir is None:
        raise ValueError("the memory toggle is on but no memory directory was given")
    if not toggles.memory and memory_dir is not None:
        raise ValueError("a memory directory was given but the memory toggle is off")
    return memory_dir


def build_graph(
    settings: RoleSettings,
    corpus: Sequence[CorpusEntry],
    client_for: ClientFor = ollama_client,
    toggles: Toggles = V2,
    memory_dir: Path | None = None,
) -> CompiledStateGraph[State, None, State, State]:
    """The compiled graph for `toggles` with the model nodes bound to `settings`, `corpus`, and
    `client_for`; B, C, and C's route are bound to the Challenger toggle, E to the lookup
    toggle, B, E, F's route, and node H to the memory toggle, H to `memory_dir`, the directory
    its files go in. Raises ValueError when `memory_dir` is missing with memory on or given with
    it off."""
    directory = _memory_directory(toggles, memory_dir)

    def b(state: State) -> State:
        return node_b(
            state, settings.describer, client_for, challenger=toggles.challenger,
            memory=toggles.memory,
        )

    def c(state: State) -> State:
        return node_c(state, toggles.challenger)

    def route_c(state: State) -> Literal["B", "D", "E", "F"]:
        return route_after_c(state, toggles.challenger)

    def d(state: State) -> State:
        return node_d(state, settings.challenger, client_for)

    def e(state: State) -> State:
        return node_e(
            state, settings.guesser, corpus, client_for, toggles.lookup, memory=toggles.memory
        )

    def route_f(state: State) -> Literal["G", "H", "end"]:
        return route_after_f(state, toggles.memory)

    graph = StateGraph(State)
    graph.add_node("G", node_g)
    graph.add_node("B", b)
    graph.add_node("C", c)
    graph.add_node("E", e)
    graph.add_node("F", node_f)
    graph.add_edge(START, "G")
    graph.add_edge("G", "B")
    graph.add_edge("B", "C")
    after_c: dict[Hashable, str] = {"B": "B", "E": "E", "F": "F"}
    if toggles.challenger:
        graph.add_node("D", d)
        after_c["D"] = "D"
        graph.add_conditional_edges("D", route_after_d, {"B": "B", "E": "E"})
    graph.add_conditional_edges("C", route_c, after_c)
    graph.add_conditional_edges("E", route_after_e, {"G": "G", "F": "F"})
    after_f: dict[Hashable, str] = {"G": "G", "end": END}
    if directory is not None:  # the memory toggle is on (checked above)

        def h(state: State) -> State:
            return node_h(state, settings.describer, settings.guesser, directory, client_for)

        graph.add_node("H", h)
        after_f["H"] = "H"
        graph.add_edge("H", END)
    graph.add_conditional_edges("F", route_f, after_f)
    return graph.compile()


def play_game(
    card_id: str,
    cards: Sequence[Card],
    corpus: Sequence[CorpusEntry],
    settings: RoleSettings,
    client_for: ClientFor = ollama_client,
    tracing: TracingClient | None = None,
    toggles: Toggles = V2,
    memory: GameMemory | None = None,
) -> State:
    """One game on the card `card_id` with the nodes `toggles` turns on: A, then the graph from
    G to the end, through H when memory is on, with the recursion limit set from the worst case.
    With memory on, `memory` gives A the two memories and the game number and H the files'
    directory. With `tracing`, A runs inside its span and the graph's config carries the
    callback handler. Raises KeyError for an unknown card id, and ValueError when `memory` is
    missing with memory on or given with it off, each before any model call; a model error
    (LLMError) propagates out of the node that hit it."""
    _memory_directory(toggles, None if memory is None else memory.directory)
    config: RunnableConfig = {"recursion_limit": RECURSION_LIMIT}

    def a() -> State:
        if memory is None:
            return node_a(card_id, cards)
        return node_a(card_id, cards, memory.describer, memory.guesser, memory.game)

    if tracing is None:
        state = a()
    else:
        with node_a_span(tracing):
            state = a()
        config["callbacks"] = [callback_handler(tracing)]
    graph = build_graph(
        settings, corpus, client_for, toggles, None if memory is None else memory.directory
    )
    final = graph.invoke(state, config=config)
    return cast(State, final)
