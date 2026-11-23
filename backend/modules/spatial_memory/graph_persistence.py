"""SQLite persistence for the Spatial Memory Theater graph."""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from backend.modules.spatial_memory.graph_physics import GraphNode

logger = logging.getLogger(__name__)


def migrate_memory_table(conn: sqlite3.Connection) -> None:
    """Safely migrate the memories table to support 3D position data."""
    columns_to_add = [
        ("pos_x", "REAL DEFAULT NULL"),
        ("pos_y", "REAL DEFAULT NULL"),
        ("pos_z", "REAL DEFAULT NULL"),
        ("cluster_id", "INTEGER DEFAULT NULL"),
    ]

    with conn:
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(f"ALTER TABLE memories ADD COLUMN {col_name} {col_type}")
                logger.info(f"Added column {col_name} to memories table.")
            except sqlite3.OperationalError:
                # Column already exists, ignore
                pass


def save_positions(conn: sqlite3.Connection, nodes: list["GraphNode"]) -> None:
    """Save current 3D positions of memory nodes back to SQLite."""
    updates = []
    for node in nodes:
        if node.memory_id is not None:
            # pos is a numpy array of shape (3,)
            updates.append(
                (
                    float(node.pos[0]),
                    float(node.pos[1]),
                    float(node.pos[2]),
                    node.memory_id,
                )
            )

    if not updates:
        return

    try:
        with conn:
            conn.executemany(
                "UPDATE memories SET pos_x=?, pos_y=?, pos_z=? WHERE id=?", updates
            )
        logger.debug("Saved %d node positions to memory database.", len(updates))
    except Exception as exc:
        logger.error("Failed to save node positions: %s", exc)


def load_positions(conn: sqlite3.Connection) -> dict[int, np.ndarray]:
    """Load previously saved 3D positions for memory nodes."""
    positions = {}
    try:
        c = conn.cursor()
        # Only select rows that have a saved position
        c.execute(
            "SELECT id, pos_x, pos_y, pos_z FROM memories WHERE pos_x IS NOT NULL"
        )
        for row in c.fetchall():
            mem_id, x, y, z = row
            positions[mem_id] = np.array([x, y, z], dtype=float)
        return positions
    except sqlite3.OperationalError as exc:
        logger.warning(
            "Could not load positions, table might not be migrated yet: %s", exc
        )
        return {}
    except Exception as exc:
        logger.error("Error loading node positions: %s", exc)
        return {}
