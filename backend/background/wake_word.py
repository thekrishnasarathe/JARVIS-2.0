"""
Wake word daemon using OpenWakeWord (offline, no API key).
Listens continuously for 'Hey JARVIS' and triggers STT pipeline.
"""
from __future__ import annotations

import logging
import threading
import numpy as np
import pyaudio
from openwakeword.model import Model

from shared.event_bus import push_event
from shared.schemas import JarvisEvent, Severity
from shared import config

logger = logging.getLogger(__name__)

# Audio config — must match OpenWakeWord requirements
SAMPLE_RATE    = 16000
CHUNK_SIZE     = 1280   # 80ms at 16kHz — OWW recommended
CHANNELS       = 1
FORMAT         = pyaudio.paInt16
WAKE_THRESHOLD = config.WAKE_THRESHOLD    # confidence threshold

_stop_event = threading.Event()

def _wake_word_loop():
    logger.info("[WAKE WORD] Initializing OpenWakeWord engine...")
    try:
        oww_model = Model(
            wakeword_models=[config.WAKE_WORD_MODEL],
            inference_framework="onnx"
        )
        logger.info("[WAKE WORD] Model loaded. Listening for 'Hey JARVIS'...")
    except Exception as e:
        logger.error(f"[WAKE WORD] Failed to load model: {e}")
        return

    try:
        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=CHANNELS,
            format=FORMAT,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )
    except Exception as e:
        logger.error(f"[WAKE WORD] Microphone error: {e}")
        if 'pa' in locals():
            pa.terminate()
        return

    logger.info("[WAKE WORD] Microphone open. Ready.")
    push_event(JarvisEvent(
        message="Wake word engine online.",
        severity=Severity.INFO,
        source="wake_word",
        data={"type": "wake_word_ready"}
    ))

    while not _stop_event.is_set():
        try:
            raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.int16)
            prediction = oww_model.predict(audio)

            for wake_word, score in prediction.items():
                if score >= WAKE_THRESHOLD:
                    logger.info(
                        f"[WAKE WORD] Detected '{wake_word}' "
                        f"(confidence: {score:.2f})"
                    )
                    _on_wake_word_detected()
                    # Brief cooldown to prevent double-trigger
                    _stop_event.wait(timeout=2.0)

        except Exception as e:
            logger.warning(f"[WAKE WORD] Audio read error: {e}")
            continue

    stream.stop_stream()
    stream.close()
    pa.terminate()
    logger.info("[WAKE WORD] Engine stopped.")

def _on_wake_word_detected():
    """Called when wake word is confirmed. Triggers STT pipeline."""
    push_event(JarvisEvent(
        message="Wake word detected — activating JARVIS...",
        severity=Severity.INFO,
        source="wake_word",
        data={"type": "wake_word_detected"}
    ))

    # Import here to avoid circular imports at module level
    from backend.background.wake_word_stt import listen_and_process
    threading.Thread(
        target=listen_and_process,
        daemon=True,
        name="WakeWordSTT"
    ).start()

def start_wake_word_engine() -> threading.Thread:
    """Start the wake word daemon. Called by run.py on startup."""
    _stop_event.clear()
    t = threading.Thread(
        target=_wake_word_loop,
        daemon=True,
        name="WakeWordEngine"
    )
    t.start()
    return t

def stop_wake_word_engine():
    """Graceful shutdown."""
    _stop_event.set()
