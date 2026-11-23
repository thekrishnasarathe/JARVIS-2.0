from __future__ import annotations

import logging
import threading

from shared import config
from shared.event_bus import push_event
from shared.schemas import JarvisEvent, Severity

logger = logging.getLogger(__name__)


def _battery_check_loop(stop_event: threading.Event) -> None:
    """Continuously monitor battery level in the background.

    Warns the user via Event Bus when battery drops below the configured
    threshold and the system is not plugged in.

    Args:
        stop_event: Set this event to cleanly terminate the loop.
    """
    warned = False  # Prevent repeating the same warning every cycle.

    while not stop_event.is_set():
        try:
            import psutil

            battery = psutil.sensors_battery()

            if battery is None:
                # Desktop PC or unsupported platform — stop polling.
                logger.info("No battery sensor detected. Monitor exiting.")
                return

            percent = battery.percent
            plugged = battery.power_plugged

            if percent <= config.BATTERY_LOW_THRESHOLD and not plugged and not warned:
                push_event(
                    JarvisEvent(
                        message=f"Battery critically low at {percent}%. Please plug in charger.",
                        severity=Severity.WARNING,
                        source="battery_monitor",
                        data={"percent": percent, "plugged": False},
                    )
                )
                warned = True
                logger.warning("Low battery warning issued: %d%%", percent)

            elif percent > config.BATTERY_LOW_THRESHOLD or plugged:
                warned = False  # Reset once battery recovers or is plugged in.

                # Push a background info event to update UI state silently
                push_event(
                    JarvisEvent(
                        message=f"Battery at {percent}%.",
                        severity=Severity.INFO,
                        source="battery_monitor",
                        data={"percent": percent, "plugged": plugged},
                    )
                )

        except Exception as exc:
            logger.error("Battery monitor error: %s", exc)

        stop_event.wait(config.BATTERY_CHECK_INTERVAL)


def start_battery_monitor() -> tuple[threading.Thread, threading.Event]:
    """Launch the battery monitor as a daemon thread.

    Returns:
        A (thread, stop_event) tuple. Set the event to stop the monitor.
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_battery_check_loop,
        args=(stop_event,),
        daemon=True,
        name="BatteryMonitor",
    )
    thread.start()
    logger.info(
        "Battery monitor started (threshold: %d%%).", config.BATTERY_LOW_THRESHOLD
    )
    return thread, stop_event
