"""Tests for Graph Physics Engine."""

import numpy as np

from backend.modules.spatial_memory.graph_physics import GraphNode, PhysicsEngine


def test_physics_engine_repulsion():
    # Two nodes at origin, they should repel
    n1 = GraphNode("1", np.array([0.0, 0.0, 0.0]), 1.0, "test", "node1", 1)
    n2 = GraphNode("2", np.array([0.0, 0.0, 0.0]), 1.0, "test", "node2", 2)

    engine = PhysicsEngine([n1, n2], [])

    # Tick should apply repulsion
    engine.tick()

    snap = engine.get_snapshot()
    pos1 = np.array(snap["1"])
    pos2 = np.array(snap["2"])

    # They shouldn't be exactly at origin anymore
    assert np.linalg.norm(pos1 - pos2) > 0.0
