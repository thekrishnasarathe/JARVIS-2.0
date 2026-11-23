"""Builds and manages the graph topology from SQLite memory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from backend.modules.spatial_memory.graph_physics import GraphNode
from shared import config

if TYPE_CHECKING:
    from backend.modules.memory import MemoryEngine

logger = logging.getLogger(__name__)

COLOR_MAP = {
    "web": (0.0, 0.8, 1.0),
    "system": (0.5, 0.2, 1.0),
    "personal": (0.0, 1.0, 0.5),
    "llm": (1.0, 0.6, 0.0),
    "default": (0.8, 0.8, 0.8),
}


def build_graph_from_memory(
    engine: "MemoryEngine",
) -> tuple[list[GraphNode], list[tuple[str, str, float]]]:
    """Extract all memories from SQLite and build the initial graph topology."""
    nodes: list[GraphNode] = []
    edges: list[tuple[str, str, float]] = []

    # 1. Fetch all rows
    c = engine.conn.cursor()
    try:
        c.execute(
            "SELECT id, category, content, importance, pos_x, pos_y, pos_z FROM memories"
        )
        rows = c.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch memories for graph builder: %s", exc)
        return [], []

    # 2. Build nodes
    memory_tokens = {}  # Cache tokenized content for TF-IDF

    for row in rows:
        mem_id = row["id"]
        category = row["category"]
        content = row["content"]
        importance = row["importance"]
        pos_x = row["pos_x"]
        pos_y = row["pos_y"]
        pos_z = row["pos_z"]

        node_id = f"mem_{mem_id}"

        if pos_x is not None and pos_y is not None and pos_z is not None:
            pos = np.array([pos_x, pos_y, pos_z], dtype=float)
        else:
            pos = np.random.uniform(-20, 20, 3)

        mass = 1.0 + (importance * 0.5)
        label = content[:40] if content else "Unknown"

        node = GraphNode(
            node_id=node_id,
            pos=pos,
            mass=mass,
            category=category,
            label=label,
            memory_id=mem_id,
        )
        nodes.append(node)

        # Tokenize
        if content:
            memory_tokens[node_id] = engine._tokenize(content)

    # 3. Compute Pairwise TF-IDF similarity for edges
    n = len(nodes)
    threshold = config.SIMILARITY_EDGE_THRESHOLD

    for i in range(n):
        id_a = nodes[i].node_id
        tokens_a = memory_tokens.get(id_a)
        if not tokens_a:
            continue

        for j in range(i + 1, n):
            id_b = nodes[j].node_id
            tokens_b = memory_tokens.get(id_b)
            if not tokens_b:
                continue

            sim = engine._cosine_similarity(tokens_a, tokens_b)
            if sim >= threshold:
                edges.append((id_a, id_b, sim))

    logger.info(
        "[THEATER] Built graph with %d nodes and %d edges.", len(nodes), len(edges)
    )
    return nodes, edges


def node_from_new_memory(
    memory_id: int, content: str, category: str, importance: int
) -> GraphNode:
    """Create a new node for a freshly inserted memory."""
    node_id = f"mem_{memory_id}"
    mass = 1.0 + (importance * 0.5)
    label = content[:40]

    # Ideally spawn near the centroid of its category.
    # Without access to the live PhysicsEngine here, we'll spawn at origin with a random offset.
    # The attraction physics will naturally pull it toward its semantically similar neighbors.
    pos = np.random.uniform(-5, 5, 3)

    return GraphNode(
        node_id=node_id,
        pos=pos,
        mass=mass,
        category=category,
        label=label,
        memory_id=memory_id,
    )
