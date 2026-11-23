"""
Post-wake-word STT pipeline.
Listens for a command, processes it, speaks the response.
"""
from __future__ import annotations

import logging
import speech_recognition as sr

from backend.core.router import process_command
from shared.event_bus import push_event
from shared.schemas import JarvisEvent, Severity

logger = logging.getLogger(__name__)
_recognizer = sr.Recognizer()
_recognizer.pause_threshold = 2.0
_recognizer.phrase_time_limit = 30

def listen_and_process():
    """Listen for one command and process it."""
    push_event(JarvisEvent(
        message="Listening...",
        severity=Severity.INFO,
        source="wake_word_stt",
        data={"type": "listening", "state": "start"}
    ))

    try:
        with sr.Microphone(sample_rate=16000) as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.3)
            logger.info("[STT] Listening for command...")
            audio = _recognizer.listen(source, timeout=8, phrase_time_limit=30)

        push_event(JarvisEvent(
            message="Processing speech...",
            severity=Severity.INFO,
            source="wake_word_stt",
            data={"type": "listening", "state": "stop"}
        ))

        query = _recognizer.recognize_google(audio)
        logger.info(f"[STT] Recognized: '{query}'")

        # Push to UI as voice interaction
        push_event(JarvisEvent(
            message=f"Voice command: {query}",
            severity=Severity.INFO,
            source="wake_word_stt",
            data={"type": "voice_interaction", "query": query}
        ))

        # Process through router
        result = process_command(query)

        # Push response to UI
        push_event(JarvisEvent(
            message=result.text,
            severity=Severity.INFO,
            source="wake_word_stt",
            data={
                "type": "voice_interaction",
                "query": query,
                "response": result.text
            }
        ))

        # Speak response via TTS
        try:
            from backend.core.tts import speak
            speak(result.text)
        except Exception as e:
            logger.warning(f"[TTS] Speech failed: {e}")

    except sr.WaitTimeoutError:
        logger.info("[STT] No speech detected after wake word.")
        push_event(JarvisEvent(
            message="No command detected.",
            severity=Severity.INFO,
            source="wake_word_stt",
            data={"type": "listening", "state": "stop"}
        ))
    except sr.UnknownValueError:
        logger.info("[STT] Could not understand audio.")
        push_event(JarvisEvent(
            message="Could not understand command.",
            severity=Severity.WARNING,
            source="wake_word_stt",
            data={"type": "listening", "state": "stop"}
        ))
    except Exception as e:
        logger.exception(f"[STT] Error: {e}")
        push_event(JarvisEvent(
            message="Voice processing error.",
            severity=Severity.ERROR,
            source="wake_word_stt",
            data={"type": "listening", "state": "stop"}
        ))
