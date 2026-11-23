"""JARVIS Task Automation module.

Handles reminders and command chaining.
"""

from __future__ import annotations

import datetime
import logging
import re
import threading

from shared.event_bus import push_event
from shared.schemas import CommandResult, JarvisEvent, Severity

logger = logging.getLogger(__name__)

_active_reminders: dict[str, dict] = {}
_reminder_counter = 0
_reminder_lock = threading.Lock()


def _fire_reminder(rem_id: str, message: str) -> None:
    with _reminder_lock:
        if rem_id in _active_reminders:
            del _active_reminders[rem_id]

    # Push event to the frontend UI
    push_event(
        JarvisEvent(
            message=f"Reminder: {message}",
            severity=Severity.WARNING,
            source="automation",
        )
    )

    # Optionally, we could also use the TTS engine to speak it
    try:
        from backend.core.tts import speak

        speak(f"Reminder: {message}")
    except Exception:
        pass


def set_reminder(query: str) -> CommandResult:
    """Set a timer-based reminder."""
    global _reminder_counter

    # Simple regex to extract minutes or seconds
    min_match = re.search(r"in (\d+) minute", query.lower())
    sec_match = re.search(r"in (\d+) second", query.lower())

    duration_secs = 0
    if min_match:
        duration_secs = int(min_match.group(1)) * 60
    elif sec_match:
        duration_secs = int(sec_match.group(1))

    if duration_secs <= 0:
        return CommandResult(
            text="Please specify a valid time, like 'remind me in 5 minutes to X'.",
            severity=Severity.WARNING,
            source="automation",
        )

    # Extract message (everything after 'to')
    msg = query
    if " to " in query.lower():
        msg = query.lower().split(" to ", 1)[1].strip()

    with _reminder_lock:
        _reminder_counter += 1
        rem_id = f"REM-{_reminder_counter}"

        timer = threading.Timer(duration_secs, _fire_reminder, args=(rem_id, msg))
        timer.daemon = True

        fire_time = datetime.datetime.now() + datetime.timedelta(seconds=duration_secs)

        _active_reminders[rem_id] = {
            "timer": timer,
            "message": msg,
            "fire_time": fire_time,
        }
        timer.start()

    return CommandResult(
        text=f"Reminder set for {msg} in {duration_secs} seconds.",
        severity=Severity.SUCCESS,
        source="automation",
    )


def list_reminders(query: str) -> CommandResult:
    """List active reminders."""
    with _reminder_lock:
        if not _active_reminders:
            return CommandResult(
                text="You have no active reminders.", source="automation"
            )

        report = "--- ACTIVE REMINDERS ---\n"
        now = datetime.datetime.now()

        for rem_id, data in _active_reminders.items():
            delta = data["fire_time"] - now
            mins = int(delta.total_seconds() // 60)
            secs = int(delta.total_seconds() % 60)
            report += f"[{rem_id}] {data['message']} (in {mins}m {secs}s)\n"

        return CommandResult(text=report.strip(), source="automation")


def cancel_reminder(query: str) -> CommandResult:
    """Cancel a reminder by ID."""
    match = re.search(r"(REM-\d+)", query.upper())
    if not match:
        return CommandResult(
            text="Please specify the reminder ID (e.g. REM-1)",
            severity=Severity.WARNING,
            source="automation",
        )

    rem_id = match.group(1)

    with _reminder_lock:
        if rem_id in _active_reminders:
            _active_reminders[rem_id]["timer"].cancel()
            del _active_reminders[rem_id]
            return CommandResult(
                text=f"Reminder {rem_id} cancelled.",
                severity=Severity.SUCCESS,
                source="automation",
            )

    return CommandResult(
        text=f"Reminder {rem_id} not found.",
        severity=Severity.WARNING,
        source="automation",
    )


def chain_commands(query: str) -> CommandResult:
    """Execute multiple commands sequentially."""
    import backend.core.router as router

    # Clean prefix
    if query.lower().startswith("do "):
        query = query[3:]

    # Split by ' then ' or ' and then '
    parts = re.split(r"\s+and then\s+|\s+then\s+", query, flags=re.IGNORECASE)

    if len(parts) < 2:
        return CommandResult(text="No chained commands found.", source="automation")

    results = []
    has_error = False

    for i, cmd in enumerate(parts):
        try:
            res = router.process_command(cmd.strip())
            results.append(f"Step {i+1} ({cmd}): {res.text}")
            if res.severity == Severity.ERROR:
                results.append("Chain halted due to error.")
                has_error = True
                break
        except Exception as exc:
            results.append(f"Step {i+1} failed: {exc}")
            has_error = True
            break

    report = "\n".join(results)
    severity = Severity.ERROR if has_error else Severity.SUCCESS

    return CommandResult(text=report, severity=severity, source="automation")
