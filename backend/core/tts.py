from __future__ import annotations

import logging
import threading

import pyttsx3

from shared import config

logger = logging.getLogger(__name__)

# ─── Thread-safety lock ──────────────────────────────────────────────
# pyttsx3 is NOT thread-safe. Background threads (battery, face monitor)
# may call speak() concurrently with the main loop. A reentrant lock
# prevents overlapping runAndWait() calls which crash the COM interface.
_tts_lock = threading.RLock()

# ─── Engine Initialization ───────────────────────────────────────────
try:
    engine = pyttsx3.init('sapi5')
except Exception as exc:
    logger.warning('SAPI5 driver failed (%s), falling back to default.', exc)
    engine = pyttsx3.init()

engine.setProperty('rate', config.TTS_RATE)

voices = engine.getProperty('voices')
if voices and len(voices) > config.TTS_VOICE_INDEX:
    engine.setProperty('voice', voices[config.TTS_VOICE_INDEX].id)

# Flush queued property changes to the COM driver immediately.
# Without this, getProperty() returns stale SAPI5 defaults until
# the first runAndWait() call — causing confusing diagnostics.
try:
    engine.runAndWait()
except Exception:
    pass  # Engine may complain about an empty speech queue; safe to ignore.


def speak(text: str) -> None:
    """Convert text to audible speech and print to console.

    Args:
        text: The string to speak aloud.

    Thread-safe: uses an RLock to serialize pyttsx3 calls from
    background daemon threads.
    """
    if not text:
        return
    print(f'JARVIS: {text}')
    with _tts_lock:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            # COM errors can occur if the engine is in a bad state;
            # log but never crash the assistant.
            logger.error('TTS engine error: %s', exc)
