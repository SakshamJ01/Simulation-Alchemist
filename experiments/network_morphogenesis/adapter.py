"""Adaptive Network Morphogenesis adapter: NDlib ContinuousModel wrapping.

Wraps NDlib's ``ContinuousModel`` for a network of nodes, each carrying a
continuous scalar *load* that diffuses via a custom weighted rule.  The adapter
owns both the NDlib model (which handles scalar diffusion) and the networkx
graph topology (which the physical system may mutate between macro-steps).

The network is **not** spatially embedded by itself -- each node carries a
fixed (x, y) pin coordinate that the coupling layer uses to place chemical
sources on the py-pde grid.

Design notes
------------
- ``native_timestep = 0.2`` (one iteration per Alchemist macro-step).
- Integer node labels required (NDlib/AGraph mishandles tuple labels in
  ``np.random.choice``).
- The custom diffusion rule is a weighted-averaging / transport rule,
  **not** a physically calibrated nutrient transport model.
- ``set_initial_status`` takes a uniform value per status name (NDlib API);
  seed nodes are set via direct mutation of ``model.status[n]`` after init.
"""

from __future__ import annotations

import warnings
from typing import Any

import networkx as nx
import numpy as np

from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet
from sim_alchemist.core.events import Event


class AdaptiveNetworkAdapter(BaseAdapter):
    """Adapter wrapping NDlib ContinuousModel for network diffusion."""

    def __init__(
        self,
        grid_rows: int = 4,
        grid_cols: int = 6,
        beta: float = 0.3,
        loss: float = 0.05,
        seed: int = 0,
        spatial_positions: dict[int, tuple[float, float]] | None = None,
    ) -> None:
        provides = CapabilitySet()
        provides.add(Capability.from_dict("network_diffusion", "1.0"))
        # The network's high-throughput-edge decision issues wall-placement
        # intentions (an agent-like signal the wall regimen consumes), so the
        # network adapter satisfies the wall pymunk adapter's
        # ``agent_intentions`` requirement without needing a Mesa component.
        provides.add(Capability.from_dict("agent_intentions", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("reaction_diffusion", "1.0"))
        requires.add(Capability.from_dict("rigid_body", "1.0"))

        super().__init__(
            engine_id="network",
            provides=provides,
            requires=requires,
            native_timestep=0.2,
        )

        self._grid_rows = grid_rows
        self._grid_cols = grid_cols
        self._beta = beta
        self._loss = loss
        self._seed = seed
        self._spatial_positions = spatial_positions

        self._graph: nx.Graph | None = None
        self._model: Any = None  # ndlib ContinuousModel
        self._node_positions: dict[int, tuple[float, float]] = {}
        self._node_to_grid: dict[int, tuple[int, int]] = {}
        self._weights: dict[tuple[int, int], float] = {}
        self._blocked: np.ndarray | None = None
        self._reset_initial: dict[int, dict[str, float]] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        import ndlib.models.ModelConfig as mc
        from ndlib.models.compartments import NodeStochastic
        from ndlib.models.ContinuousModel import ContinuousModel

        super().initialize(config)

        g = nx.grid_2d_graph(self._grid_rows, self._grid_cols)
        mapping = {n: i for i, n in enumerate(g.nodes())}
        self._graph = nx.relabel_nodes(g, mapping)
        graph = self._graph
        assert graph is not None

        for tuple_node, int_node in mapping.items():
            row, col = tuple_node
            if self._spatial_positions and int_node in self._spatial_positions:
                self._node_positions[int_node] = self._spatial_positions[int_node]
            else:
                self._node_positions[int_node] = (
                    (col + 0.5) / self._grid_cols,
                    (row + 0.5) / self._grid_rows,
                )
            self._node_to_grid[int_node] = (row, col)

        np.random.seed(self._seed)
        self._model = ContinuousModel(
            graph,
            constants={
                "beta": self._beta,
                "loss": self._loss,
                "weights": self._weights,
            },
        )
        self._model.add_status("loaded")

        nd_config = mc.Configuration()
        nd_config.add_model_parameter("fraction_infected", 0.0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._model.set_initial_status({"loaded": 0.0}, nd_config)

        # Repin the generator: NDlib's internal fraction_infected sampling
        # consumes draws even when the ContinuousModel status dict overwrites
        # them, so re-seed to keep diffusion steps independent of that bookkeeping.
        np.random.seed(self._seed)

        rule = NodeStochastic(1.0)
        self._model.add_rule("loaded", _diffuse_rule, rule)

        self._weights = {}
        for u, v in graph.edges():
            self._weights[(u, v)] = 1.0
            self._weights[(v, u)] = 1.0

        self._model.constants["weights"] = self._weights

        self._blocked = np.zeros(
            (self._grid_rows, self._grid_cols), dtype=bool
        )

        seed_loads = self._initial_seed_loads()
        for n in graph.nodes:
            self._model.status[n]["loaded"] = seed_loads.get(n, 0.0)

        self._reset_initial = {
            n: {"loaded": seed_loads.get(n, 0.0)} for n in graph.nodes
        }

    def _initial_seed_loads(self) -> dict[int, float]:
        """Seed half of the grid-corner nodes with unit load.

        Everything else starts empty, so the network has a clear load
        gradient that diffusion smooths and the coupling can act on without
        needing any externally supplied initial condition.
        """
        seeds: dict[int, float] = {}
        corners = {
            0,
            self._grid_cols - 1,
            (self._grid_rows - 1) * self._grid_cols,
            self._grid_rows * self._grid_cols - 1,
        }
        for i, node in enumerate(sorted(corners)):
            if i % 2 == 0:
                seeds[node] = 1.0
        return seeds

    def step(self, dt: float) -> None:
        if self._model is None:
            return
        self._model.iteration()

    def get_state(self) -> dict[str, Any]:
        if self._model is None:
            return {}
        return {
            "load": {
                n: s.get("loaded", 0.0)
                for n, s in self._model.status.items()
            },
            "positions": dict(self._node_positions),
            "weights": dict(self._weights),
        }

    def get_load(self) -> dict[int, float]:
        if self._model is None:
            return {}
        return {
            n: s.get("loaded", 0.0)
            for n, s in self._model.status.items()
        }

    def set_load(self, loads: dict[int, float]) -> None:
        if self._model is None:
            return
        for n, val in loads.items():
            if n in self._model.status:
                self._model.status[n]["loaded"] = float(val)

    def seed_node_ids(self) -> list[int]:
        """Return the reservoir node ids (seeded corners)."""
        return [n for n, v in self._initial_seed_loads().items() if v > 0.0]

    def nourish_reservoirs(self) -> None:
        """Recharge the reservoir nodes to unit load each macro step.

        Without this, loads decay/saturate and the network relaxes to
        uniformity.  Pinning the reservoirs sustains a persistent load
        gradient for the whole run, so the coupling keeps responding.
        """
        if self._model is None:
            return
        for n in self.seed_node_ids():
            if n in self._model.status:
                self._model.status[n]["loaded"] = 1.0

    def set_blocked(self, blocked: np.ndarray) -> None:
        self._blocked = blocked

    def reweight_from_geometry(self) -> None:
        g = self._graph
        if g is None or self._blocked is None or self._model is None:
            return
        n_r = self._blocked.shape[0]
        n_c = self._blocked.shape[1]
        for u, v in list(g.edges()):
            ru, cu = self._node_to_grid[u]
            rv, cv = self._node_to_grid[v]
            mid_r = (ru + rv) / 2.0
            mid_c = (cu + cv) / 2.0
            bi = int(np.clip(round(mid_r), 0, n_r - 1))
            bj = int(np.clip(round(mid_c), 0, n_c - 1))
            blocked_factor = 0.1 if self._blocked[bi, bj] else 1.0
            self._weights[(u, v)] = 1.0 * blocked_factor
            self._weights[(v, u)] = 1.0 * blocked_factor

    def get_highest_throughput_edge(
        self, loads: dict[int, float]
    ) -> tuple[int, int] | None:
        g = self._graph
        if g is None:
            return None
        best_edge = None
        best_throughput = -1.0
        for u, v in g.edges():
            w = self._weights.get((u, v), 1.0)
            lu = loads.get(u, 0.0)
            lv = loads.get(v, 0.0)
            throughput = w * (lu + lv) / 2.0
            if throughput > best_throughput:
                best_throughput = throughput
                best_edge = (u, v)
        return best_edge

    def get_node_positions(self) -> dict[int, tuple[float, float]]:
        return dict(self._node_positions)

    def reset(self) -> None:
        if self._model is None:
            return
        g = self._graph
        if g is None:
            return
        self._model.reset()
        np.random.seed(self._seed)
        seed_loads = self._initial_seed_loads()
        for n in g.nodes():
            self._model.status[n] = {"loaded": seed_loads.get(n, 0.0)}
        self._weights = {}
        for u, v in g.edges():
            self._weights[(u, v)] = 1.0
            self._weights[(v, u)] = 1.0
        self._model.constants["weights"] = self._weights
        self._model.actual_iteration = 0
        self._model.initial_status = {
            n: {"loaded": seed_loads.get(n, 0.0)} for n in g.nodes()
        }

    def apply_event(self, event: Event) -> bool:
        return False

    def shutdown(self) -> None:
        self._model = None
        self._graph = None
        self._weights.clear()


def _diffuse_rule(
    node: int,
    graph: Any,
    status: dict,
    attrs: Any,
    constants: dict,
) -> float:
    my_load = status[node].get("loaded", 0.0)
    neighbors = list(graph.neighbors(node))
    if not neighbors:
        return my_load

    weights = constants["weights"]
    beta = constants["beta"]
    loss = constants["loss"]

    weighted_sum = 0.0
    weight_total = 0.0
    for nbr in neighbors:
        w = weights.get((node, nbr), 1.0)
        weighted_sum += w * status[nbr].get("loaded", 0.0)
        weight_total += w

    if weight_total <= 0.0:
        avg = 0.0
    else:
        avg = weighted_sum / weight_total

    new_val = (1.0 - loss) * my_load + beta * avg
    return max(0.0, min(1.0, new_val))
