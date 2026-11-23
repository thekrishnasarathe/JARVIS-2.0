"""Force-directed graph physics engine for Spatial Memory Theater."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from shared import config
from shared.event_bus import push_event
from shared.schemas import JarvisEvent, Severity

logger = logging.getLogger(__name__)


class GraphNode:
    """A single memory node in 3D space."""

    def __init__(
        self,
        node_id: str,
        pos: np.ndarray,
        mass: float,
        category: str,
        label: str,
        memory_id: Optional[int] = None,
    ):
        self.node_id = node_id
        self.pos = pos
        self.vel = np.zeros(3, dtype=float)
        self.mass = mass
        self.category = category
        self.label = label
        self.memory_id = memory_id

        self.is_live = False
        self.live_decay = 0.0


class PhysicsEngine:
    """Simulates force-directed graph physics in a background thread."""

    REPULSION_K = 15.0
    ATTRACTION_K = 0.08
    DAMPING = 0.85
    MAX_VELOCITY = 2.0

    def __init__(self, nodes: list[GraphNode], edges: list[tuple[str, str, float]]):
        self._lock = threading.Lock()

        # Internal state
        self.nodes = {node.node_id: node for node in nodes}
        # edges stored as adjacency list for faster lookup
        # self.edges[node_a] = [(node_b, weight), ...]
        self.edges: dict[str, list[tuple[str, float]]] = {
            node_id: [] for node_id in self.nodes
        }
        self._all_edges_list = edges  # flat list of (a, b, weight)

        for a, b, weight in edges:
            if a in self.nodes and b in self.nodes:
                self.edges[a].append((b, weight))
                self.edges[b].append((a, weight))

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background physics simulation thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="TheaterPhysics", daemon=True
        )
        self._thread.start()
        logger.info("PhysicsEngine started.")

    def stop(self) -> None:
        """Stop the background physics simulation thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("PhysicsEngine stopped.")

    def add_node(self, node: GraphNode) -> None:
        """Thread-safe addition of a new node."""
        with self._lock:
            self.nodes[node.node_id] = node
            if node.node_id not in self.edges:
                self.edges[node.node_id] = []

    def add_edge(self, node_id_a: str, node_id_b: str, weight: float) -> None:
        """Thread-safe addition of a new edge."""
        with self._lock:
            if node_id_a in self.nodes and node_id_b in self.nodes:
                self.edges[node_id_a].append((node_id_b, weight))
                self.edges[node_id_b].append((node_id_a, weight))
                self._all_edges_list.append((node_id_a, node_id_b, weight))

    def get_snapshot(self) -> dict[str, list[float]]:
        """Return a thread-safe deepcopy of current node positions."""
        snapshot = {}
        with self._lock:
            for node_id, node in self.nodes.items():
                snapshot[node_id] = node.pos.tolist()
        return snapshot

    def _loop(self) -> None:
        """The main simulation loop."""
        tick_interval = config.PHYSICS_TICK_MS / 1000.0

        # Save graph hook
        last_save = time.time()

        while not self._stop_event.is_set():
            start_time = time.time()

            self.tick()

            # Periodic saving
            if start_time - last_save > config.GRAPH_SAVE_INTERVAL_S:
                self._trigger_save()
                last_save = start_time

            elapsed = time.time() - start_time
            sleep_time = max(0.01, tick_interval - elapsed)
            self._stop_event.wait(sleep_time)

    def _trigger_save(self) -> None:
        """Triggers a background save to SQLite."""
        try:
            from backend.modules.spatial_memory.graph_persistence import save_positions
            from backend.modules.memory import get_engine

            engine = get_engine()
            with self._lock:
                # Copy the list of nodes so we don't hold the lock during DB IO
                nodes_to_save = list(self.nodes.values())

            save_positions(engine.conn, nodes_to_save)
        except Exception as exc:
            logger.error("Physics auto-save failed: %s", exc)

    def tick(self) -> None:
        """Perform one physics tick."""
        with self._lock:
            node_ids = list(self.nodes.keys())
            n = len(node_ids)
            if n < 2:
                return

            # Forces dictionary
            forces = {nid: np.zeros(3, dtype=float) for nid in node_ids}

            # 1. Repulsion (all pairs)
            for i in range(n):
                for j in range(i + 1, n):
                    id_a = node_ids[i]
                    id_b = node_ids[j]
                    node_a = self.nodes[id_a]
                    node_b = self.nodes[id_b]

                    diff = node_a.pos - node_b.pos
                    dist_sq = np.sum(diff**2)

                    # Prevent division by zero
                    if dist_sq < 0.1:
                        dist_sq = 0.1
                        # Give a random nudge if perfectly overlapping
                        diff = np.random.uniform(-0.1, 0.1, 3)

                    dist = np.sqrt(dist_sq)

                    # F = k / d^2
                    force_mag = self.REPULSION_K / dist_sq
                    force_vec = (diff / dist) * force_mag

                    forces[id_a] += force_vec
                    forces[id_b] -= force_vec

            # 2. Attraction (edges)
            for id_a, edges_list in self.edges.items():
                node_a = self.nodes[id_a]
                for id_b, weight in edges_list:
                    # To avoid double-counting, only do a->b if a < b
                    if id_a >= id_b:
                        continue

                    node_b = self.nodes[id_b]
                    diff = node_b.pos - node_a.pos
                    dist = np.linalg.norm(diff)

                    if dist > 0.01:
                        # Hooke's Law: F = k * x (scaled by edge weight)
                        force_mag = self.ATTRACTION_K * weight * dist
                        force_vec = (diff / dist) * force_mag

                        forces[id_a] += force_vec
                        forces[id_b] -= force_vec

            # 3. Central gravity (pull everything slowly to origin to avoid drifting to infinity)
            # F = -k * pos
            CENTRAL_GRAVITY = 0.01
            for nid in node_ids:
                forces[nid] -= self.nodes[nid].pos * CENTRAL_GRAVITY

            # 4. Apply forces -> Velocity -> Position
            positions_payload = {}
            for nid in node_ids:
                node = self.nodes[nid]

                # a = F/m
                acceleration = forces[nid] / node.mass

                # v = (v + a) * damping
                node.vel = (node.vel + acceleration) * self.DAMPING

                # Clamp velocity
                speed = np.linalg.norm(node.vel)
                if speed > self.MAX_VELOCITY:
                    node.vel = (node.vel / speed) * self.MAX_VELOCITY

                # Update position
                node.pos += node.vel
                positions_payload[nid] = node.pos.tolist()

        # Emit the position update to the UI
        push_event(
            JarvisEvent(
                message="Physics update",
                severity=Severity.INFO,
                source="physics",
                data={"type": "theater_tick", "positions": positions_payload},
            )
        )
