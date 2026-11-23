"""Thread-safe event bus for backend→frontend communication.

Background daemon threads (battery monitor, face monitor) push JarvisEvent
objects into this bus. The Reflex frontend polls the bus via an
@rx.background task and renders events as toasts / state updates.

Architecture:
    Producer (threading.Thread) → queue.Queue → Consumer (asyncio coroutine)

The queue.Queue is inherently thread-safe. The async consumer wraps
queue.get() in asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import queue
from typing import Optional

from shared.schemas import JarvisEvent

logger = logging.getLogger(__name__)

# Module-level singleton queue. Thread-safe by design.
_event_queue: queue.Queue[JarvisEvent] = queue.Queue(maxsize=256)


def push_event(event: JarvisEvent) -> None:
    """Push an event from any thread (blocking producer side).

    If the queue is full, the oldest event is silently dropped
    and a warning is logged. This prevents a stuck consumer from
    causing unbounded memory growth.

    Args:
        event: The event to enqueue.
    """
    try:
        _event_queue.put_nowait(event)
        logger.debug("Event pushed: %s", event.message)
    except queue.Full:
        # Drop oldest to make room — bounded buffer strategy.
        try:
            _event_queue.get_nowait()
        except queue.Empty:
            pass
        _event_queue.put_nowait(event)
        logger.warning("Event bus full — dropped oldest event.")


async def poll_event(timeout: float = 0.5) -> Optional[JarvisEvent]:
    """Async-safe event consumer for Reflex background tasks.

    Wraps the blocking queue.get() in asyncio.to_thread() so the
    Reflex event loop is never blocked.

    Args:
        timeout: Maximum seconds to wait for an event.

    Returns:
        A JarvisEvent if one was available, or None on timeout.
    """
    try:
        event = await asyncio.to_thread(_event_queue.get, timeout=timeout)
        return event
    except queue.Empty:
        return None


def drain_all() -> list[JarvisEvent]:
    """Drain all pending events (synchronous, non-blocking).

    Useful for batch-processing on page load.

    Returns:
        A list of all queued events (may be empty).
    """
    events: list[JarvisEvent] = []
    while True:
        try:
            events.append(_event_queue.get_nowait())
        except queue.Empty:
            break
    return events
