"""Pomodoro Timer — Demo Plugin #2 for JARVIS 2.0.

Starts a non-blocking background timer that pushes a JarvisEvent
when the work session is over. Default duration: 25 minutes.
"""

from __future__ import annotations

import logging
import re
import threading

from shared.event_bus import push_event
from shared.schemas import CommandResult, JarvisEvent, Severity

logger = logging.getLogger(__name__)

PLUGIN_NAME = "pomodoro"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "Krishna Sarathe"

_DEFAULT_MINUTES = 25

# Keep references to active timers so they can be cancelled on unload
_active_timers: list[threading.Timer] = []
_timer_lock = threading.Lock()


def _wants_pomodoro(query: str) -> bool:
    triggers = {"pomodoro", "focus timer", "start timer", "work timer"}
    return any(t in query for t in triggers)


def _parse_duration(query: str) -> int:
    """Extract a numeric duration in minutes from the query string."""
    match = re.search(r"(\d+)\s*(?:minute|min|m)", query)
    if match:
        return max(1, int(match.group(1)))
    return _DEFAULT_MINUTES


def _on_timer_complete(minutes: int) -> None:
    """Callback fired when the pomodoro timer expires."""
    logger.info("[PLUGIN:%s] Pomodoro complete (%d min)", PLUGIN_NAME, minutes)
    push_event(
        JarvisEvent(
            message=f"Pomodoro complete! You focused for {minutes} minutes. Take a break!",
            severity=Severity.SUCCESS,
            source=PLUGIN_NAME,
            data={"type": "pomodoro_complete", "minutes": minutes},
        )
    )


def _start_pomodoro(query: str) -> CommandResult:
    """Parse duration and start a background timer."""
    minutes = _parse_duration(query)
    seconds = minutes * 60

    timer = threading.Timer(seconds, _on_timer_complete, args=(minutes,))
    timer.daemon = True
    timer.start()

    with _timer_lock:
        _active_timers.append(timer)

    logger.info(
        "[PLUGIN:%s] Pomodoro started: %d min (%d sec)", PLUGIN_NAME, minutes, seconds
    )

    return CommandResult(
        text=f"Pomodoro started. I'll alert you in {minutes} minutes. Stay focused!",
        severity=Severity.SUCCESS,
        source=PLUGIN_NAME,
    )


def on_unload() -> None:
    """Cancel any active timers on graceful shutdown."""
    with _timer_lock:
        for timer in _active_timers:
            timer.cancel()
        _active_timers.clear()
    logger.info("[PLUGIN:%s] All active timers cancelled.", PLUGIN_NAME)


COMMANDS = [
    (_wants_pomodoro, _start_pomodoro, "Starts a Pomodoro focus timer"),
]
