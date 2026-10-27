"""The V2 graph of one game (Full flow of one game, the V2 column): G, B, C, D, E, and F as one
LangGraph graph, and `play_game`, which runs it on one card.

Node A is not a graph node: `node_a` builds the initial State from the card id, and the
graph starts at G with that State as its input, so an unknown card id raises before any model
call (A → G is kept). The model nodes B, D, and E take their ModelSettings, the client factory,
and (E) the corpus beside State; `build_graph` wraps each in a closure, so every graph node is
`State -> State`. The routers are the node modules' own (`route_after_c`, `route_after_d`,
`route_after_e`, `route_after_f`); they return single-letter node names, which are the node
names here.

Edges, the V2 column: G → B; B → C; C → B (send-back), D (description), E (answer), or F
(violation); D → B (reject) or E (pass or forced pass); E → G (valid question) or F (guess or
violation); F → G (new round) or the end. For now a description always goes to D; the V0–V1 edge
C → E for a description is not built yet.

The recursion limit is set explicitly from the worst case (see `WORST_CASE_STEPS`), never from
LangGraph's default: langgraph 1.2.16 defaults to 10007 steps, earlier versions to 25, below a
ten-round V2 game.

Tracing (`SPEC.md` Milestones, M3): given a `TracingClient` (`tracing.py`), `play_game` runs node A
inside its span and passes the Langfuse callback handler in the graph's config, so each node visit
is a chain span named by the node's single-letter name, matching the node table in `SPEC.md` Full
flow of one game, under the game span `play.main` opens."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from dont_say_oyster.cards import Card
from dont_say_oyster.challenger import REJECT_LIMIT, node_d, route_after_d
from dont_say_oyster.corpus import CorpusEntry
from dont_say_oyster.describer import node_b
from dont_say_oyster.guesser import node_e, route_after_e
from dont_say_oyster.llm import ClientFor, ModelSettings, ollama_client
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
DESCRIPTIONS_PER_ROUND = REJECT_LIMIT + 1
B_C_VISITS_PER_DESCRIPTION = (SEND_BACKS + 1) * 2
STEPS_PER_ROUND = (
    1  # G
    + DESCRIPTIONS_PER_ROUND * B_C_VISITS_PER_DESCRIPTION  # 3 × 6 = 18
    + DESCRIPTIONS_PER_ROUND  # D
    + 1  # E
    + 1  # F
)
WORST_CASE_STEPS = ROUNDS * STEPS_PER_ROUND  # 10 × 24 = 240
RECURSION_LIMIT = WORST_CASE_STEPS + 60  # the required +1 and a margin; 300


def build_graph(
    settings: RoleSettings,
    corpus: Sequence[CorpusEntry],
    client_for: ClientFor = ollama_client,
) -> CompiledStateGraph[State, None, State, State]:
    """The compiled V2 graph with the model nodes bound to `settings`, `corpus`, and
    `client_for`."""

    def b(state: State) -> State:
        return node_b(state, settings.describer, client_for)

    def d(state: State) -> State:
        return node_d(state, settings.challenger, client_for)

    def e(state: State) -> State:
        return node_e(state, settings.guesser, corpus, client_for)

    graph = StateGraph(State)
    graph.add_node("G", node_g)
    graph.add_node("B", b)
    graph.add_node("C", node_c)
    graph.add_node("D", d)
    graph.add_node("E", e)
    graph.add_node("F", node_f)
    graph.add_edge(START, "G")
    graph.add_edge("G", "B")
    graph.add_edge("B", "C")
    graph.add_conditional_edges("C", route_after_c, {"B": "B", "D": "D", "E": "E", "F": "F"})
    graph.add_conditional_edges("D", route_after_d, {"B": "B", "E": "E"})
    graph.add_conditional_edges("E", route_after_e, {"G": "G", "F": "F"})
    graph.add_conditional_edges("F", route_after_f, {"G": "G", "end": END})
    return graph.compile()


def play_game(
    card_id: str,
    cards: Sequence[Card],
    corpus: Sequence[CorpusEntry],
    settings: RoleSettings,
    client_for: ClientFor = ollama_client,
    tracing: TracingClient | None = None,
) -> State:
    """One V2 game on the card `card_id`: A, then the graph from G to the end, with the
    recursion limit set from the worst case. With `tracing`, A runs inside its span and the
    graph's config carries the callback handler. Raises KeyError for an unknown card id before
    any model call; a model error (LLMError) propagates out of the node that hit it."""
    config: RunnableConfig = {"recursion_limit": RECURSION_LIMIT}
    if tracing is None:
        state = node_a(card_id, cards)
    else:
        with node_a_span(tracing):
            state = node_a(card_id, cards)
        config["callbacks"] = [callback_handler(tracing)]
    graph = build_graph(settings, corpus, client_for)
    final = graph.invoke(state, config=config)
    return cast(State, final)
