"""Tests for Graph Persistence."""

import sqlite3

import numpy as np

from backend.modules.spatial_memory.graph_persistence import (
    load_positions,
    migrate_memory_table,
    save_positions,
)
from backend.modules.spatial_memory.graph_physics import GraphNode


def test_graph_persistence_roundtrip():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT
        )
    """)
    conn.execute("INSERT INTO memories (content) VALUES ('test')")

    # Migrate
    migrate_memory_table(conn)

    # Save positions
    n1 = GraphNode("mem_1", np.array([1.5, -2.0, 3.14]), 1.0, "test", "label", 1)
    save_positions(conn, [n1])

    # Load positions
    positions = load_positions(conn)
    assert 1 in positions
    np.testing.assert_allclose(positions[1], np.array([1.5, -2.0, 3.14]))
