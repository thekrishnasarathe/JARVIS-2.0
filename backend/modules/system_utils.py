"""System utility commands: date/time, battery, screenshots, notes."""
from __future__ import annotations

import datetime
import logging
import os

from shared import config
from shared.schemas import CommandResult, Severity
from backend.core.stt import take_command

logger = logging.getLogger(__name__)


def tell_datetime(query: str) -> CommandResult:
    """Return the current date and/or time based on what the user asked.

    Args:
        query: The user's voice command.
    """
    now = datetime.datetime.now()
    query_lower = query.lower()

    has_date = 'date' in query_lower
    has_time = 'time' in query_lower

    if has_date and not has_time:
        text = f'Today\'s date is {now.strftime("%B %d, %Y")}.'
    elif has_time and not has_date:
        text = f'The time is {now.strftime("%I:%M %p")}.'
    else:
        text = (
            f'Today is {now.strftime("%B %d, %Y")} '
            f'and the time is {now.strftime("%I:%M %p")}.'
        )

    return CommandResult(text=text, source="system_utils")


def check_battery(query: str) -> CommandResult:
    """Report current battery percentage and charging status.

    Args:
        query: The user's voice command (unused but required by interface).
    """
    try:
        import psutil
        battery = psutil.sensors_battery()

        if battery is None:
            return CommandResult(
                text='No battery detected. You are probably on a desktop PC.',
                source="system_utils",
            )

        percent = battery.percent
        plugged = battery.power_plugged
        status = 'plugged in' if plugged else 'not plugged in'
        text = f'Battery is at {percent} percent and {status}.'
        
        severity = Severity.WARNING if percent <= config.BATTERY_LOW_THRESHOLD and not plugged else Severity.INFO
        return CommandResult(text=text, severity=severity, source="system_utils")

    except ImportError:
        logger.error('psutil is not installed.')
        return CommandResult(
            text='The battery monitoring library is not installed.',
            severity=Severity.ERROR,
            source="system_utils",
        )
    except Exception as exc:
        logger.error('Battery check error: %s', exc)
        return CommandResult(
            text='Sorry, I could not check the battery status.',
            severity=Severity.ERROR,
            source="system_utils",
        )


def take_screenshot(query: str) -> CommandResult:
    """Capture a screenshot and save it to the desktop.

    Args:
        query: The user's voice command (unused but required by interface).
    """
    try:
        import pyautogui

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screenshot_{timestamp}.png'
        filepath = os.path.join(config.DESKTOP_PATH, filename)

        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)

        logger.info('Screenshot saved to %s', filepath)
        return CommandResult(
            text=f'Screenshot saved as {filename}.',
            severity=Severity.SUCCESS,
            source="system_utils",
        )

    except ImportError:
        logger.error('pyautogui is not installed.')
        return CommandResult(
            text='The screenshot library is not installed.',
            severity=Severity.ERROR,
            source="system_utils",
        )
    except Exception as exc:
        logger.error('Screenshot error: %s', exc)
        return CommandResult(
            text='Sorry, I could not take the screenshot.',
            severity=Severity.ERROR,
            source="system_utils",
        )


def take_note(query: str) -> CommandResult:
    """Prompt the user for a note and append it to the notes file.

    Args:
        query: The user's voice command (unused but required by interface).
    """
    query_lower = query.lower()
    note_text = ""
    
    for keyword in ['note that ', 'note ', 'dictation ']:
        if keyword in query_lower:
            # Case-insensitive split but retain original case of the note
            idx = query_lower.find(keyword)
            extracted = query[idx + len(keyword):].strip()
            if extracted:
                note_text = extracted
                break

    if not note_text:
        # Fallback to voice if no text provided in the command
        from backend.core.tts import speak
        speak('What should I write down?')
        note_text = take_command()

    if note_text == 'None' or not note_text:
        return CommandResult(
            text="I didn't catch that. Note was not saved.",
            severity=Severity.WARNING,
            source="system_utils",
        )

    try:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        os.makedirs(os.path.dirname(config.NOTES_FILE), exist_ok=True)

        with open(config.NOTES_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{timestamp}] {note_text}\n')

        logger.info('Note appended to %s', config.NOTES_FILE)
        return CommandResult(
            text='Note saved successfully.',
            severity=Severity.SUCCESS,
            source="system_utils",
        )

    except Exception as exc:
        logger.error('Note-taking error: %s', exc)
        return CommandResult(
            text='Sorry, I could not save the note.',
            severity=Severity.ERROR,
            source="system_utils",
        )


def play_youtube(query: str) -> CommandResult:
    """Play the first YouTube search result for the given query.

    Args:
        query: The user's voice command, expected to start with 'play '.
    """
    try:
        import pywhatkit
    except ImportError:
        logger.error('pywhatkit is not installed.')
        return CommandResult(
            text='The YouTube playback library is not installed.',
            severity=Severity.ERROR,
            source="system_utils",
        )

    search_term = query.lower().removeprefix('play ').strip()

    if not search_term:
        return CommandResult(
            text='Please tell me what to play on YouTube.',
            severity=Severity.WARNING,
            source="system_utils",
        )

    try:
        pywhatkit.playonyt(search_term)
        return CommandResult(
            text=f'Playing {search_term} on YouTube.',
            severity=Severity.SUCCESS,
            source="system_utils",
        )
    except Exception as exc:
        logger.error('YouTube playback error: %s', exc)
        return CommandResult(
            text='Sorry, I could not play that on YouTube.',
            severity=Severity.ERROR,
            source="system_utils",
        )


def google_search(query: str) -> CommandResult:
    """Perform a Google search for the given query.

    Args:
        query: The user's voice command.
    """
    try:
        import pywhatkit
    except ImportError:
        logger.error('pywhatkit is not installed.')
        return CommandResult(
            text='The pywhatkit library is not installed.',
            severity=Severity.ERROR,
            source="system_utils",
        )

    search_term = query.lower().replace('google search', '').replace('search google for', '').strip()

    if not search_term:
        return CommandResult(
            text='Please tell me what to search for on Google.',
            severity=Severity.WARNING,
            source="system_utils",
        )

    try:
        pywhatkit.search(search_term)
        return CommandResult(
            text=f'Searching Google for {search_term}.',
            severity=Severity.SUCCESS,
            source="system_utils",
        )
    except Exception as exc:
        logger.error('Google search error: %s', exc)
        return CommandResult(
            text='Sorry, I could not perform the Google search.',
            severity=Severity.ERROR,
            source="system_utils",
        )
