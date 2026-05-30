"""Shared data schemas for cross-boundary communication."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """Event severity levels for UI rendering."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Structured response from a JARVIS command handler.

    Replaces the old `bool` return + side-effecting `speak()` pattern.

    Attributes:
        text: The response text (what JARVIS would "say").
        continue_loop: Whether the main loop should continue (False = exit).
        severity: UI hint for toast/card coloring.
        source: Which module generated this result.
    """
    text: str
    continue_loop: bool = True
    severity: Severity = Severity.INFO
    source: str = "jarvis"


@dataclass(frozen=True, slots=True)
class JarvisEvent:
    """An event pushed from a background thread to the frontend.

    Attributes:
        message: Human-readable event description.
        severity: Severity level for UI rendering.
        source: Originating subsystem (e.g., "battery_monitor").
        timestamp: When the event was generated.
        data: Optional structured payload (e.g., battery percent).
    """
    message: str
    severity: Severity = Severity.WARNING
    source: str = "system"
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    data: Optional[dict] = None
