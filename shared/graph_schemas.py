"""Shared dataclasses for Memory Theater graph events."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NodeEvent:
    """Payload for node-level visual events in the Memory Theater."""

    node_id: str
    event_type: str  # "spawn", "activate", "pulse", "merge"
    color: tuple[float, float, float]  # RGB 0.0-1.0
    intensity: float = 1.0
    duration_ms: int = 800
