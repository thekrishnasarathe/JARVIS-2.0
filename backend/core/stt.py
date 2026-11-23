from __future__ import annotations

import logging

import speech_recognition as sr

logger = logging.getLogger(__name__)

# Sentinel value returned when recognition fails.
_RECOGNITION_FAILURE: str = "None"


def take_command(timeout: int = 10, language: str = "en-in") -> str:
    """Listen to the microphone and convert speech to text.

    Blocks until the user finishes speaking or the timeout expires.

    Args:
        timeout: Maximum seconds to wait for speech onset.
        language: BCP-47 language tag for Google Speech Recognition.

    Returns:
        The recognized string, or the sentinel 'None' on failure.
    """
    recognizer = sr.Recognizer()

    try:
        with sr.Microphone() as source:
            print("Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            recognizer.pause_threshold = 2       # Wait 2s of silence before cutting off
            recognizer.phrase_threshold = 0.3     # Min 0.3s of audio to count as speech
            recognizer.non_speaking_duration = 0.8  # Keep listening through brief pauses
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=30)

        print("Recognizing...")
        query: str = recognizer.recognize_google(audio, language=language)
        print(f"User said: {query}\n")
        return query

    except sr.UnknownValueError:
        logger.debug("Speech was unintelligible.")
        return _RECOGNITION_FAILURE
    except sr.RequestError as exc:
        logger.error("Google Speech Recognition service error: %s", exc)
        return _RECOGNITION_FAILURE
    except Exception as exc:
        logger.error("Microphone / audio error: %s", exc)
        return _RECOGNITION_FAILURE
