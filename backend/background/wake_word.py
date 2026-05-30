"""Wake Word background daemon using pvporcupine.

Listens for the 'Jarvis' hotword and bridges to the STT pipeline.
"""
from __future__ import annotations

import logging
import struct
import threading

import pyaudio
import pvporcupine

from shared import config
from shared.event_bus import push_event
from shared.schemas import JarvisEvent, Severity

logger = logging.getLogger(__name__)

def _wake_word_loop(stop_event: threading.Event) -> None:
    """Continuously listen for the wake word."""
    porcupine = None
    pa = None
    audio_stream = None

    try:
        if config.PORCUPINE_ACCESS_KEY == "YOUR_PORCUPINE_ACCESS_KEY" or not config.PORCUPINE_ACCESS_KEY:
            raise ValueError("Porcupine access key not configured.")

        porcupine = pvporcupine.create(
            access_key=config.PORCUPINE_ACCESS_KEY,
            keywords=config.PORCUPINE_KEYWORDS
        )
        
        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length
        )

        logger.info("Wake-word engine started. Listening for %s...", config.PORCUPINE_KEYWORDS)
        
        while not stop_event.is_set():
            pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)

            keyword_index = porcupine.process(pcm)
            
            if keyword_index >= 0:
                logger.info("Wake word detected!")
                
                # Signal UI that we are listening
                push_event(JarvisEvent(
                    message="Listening for voice command...",
                    severity=Severity.INFO,
                    source="wake_word",
                    data={"type": "listening", "state": "start"}
                ))
                
                # Temporarily stop the audio stream so STT can use the microphone
                audio_stream.stop_stream()
                
                try:
                    from backend.core.stt import take_command
                    query = take_command()
                    
                    if query and query != 'None':
                        from backend.core.router import process_command
                        result = process_command(query)
                        
                        # Push event with the transcribed query and the result so the UI can render it
                        push_event(JarvisEvent(
                            message=f"Voice query processed: {query}",
                            severity=Severity.INFO,
                            source="wake_word",
                            data={
                                "type": "voice_interaction", 
                                "query": query, 
                                "response": result.text
                            }
                        ))
                except Exception as e:
                    logger.error("Error during STT or routing: %s", e)
                finally:
                    # Signal UI that we stopped listening
                    push_event(JarvisEvent(
                        message="Stopped listening.",
                        severity=Severity.INFO,
                        source="wake_word",
                        data={"type": "listening", "state": "stop"}
                    ))
                    
                    # Restart stream for wake-word
                    if not stop_event.is_set():
                        audio_stream.start_stream()

    except ValueError as ve:
        logger.error("Wake word engine disabled: %s", ve)
        push_event(JarvisEvent(
            message="Wake-word engine disabled: Missing API key. Please update .env",
            severity=Severity.ERROR,
            source="wake_word"
        ))
    except Exception as exc:
        logger.error("Wake word engine crashed: %s", exc)
        push_event(JarvisEvent(
            message=f"Wake-word engine crashed: {exc}",
            severity=Severity.ERROR,
            source="wake_word"
        ))
    finally:
        if audio_stream is not None:
            audio_stream.close()
        if pa is not None:
            pa.terminate()
        if porcupine is not None:
            porcupine.delete()


def start_wake_word_engine() -> tuple[threading.Thread, threading.Event]:
    """Launch the wake-word engine as a daemon thread."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_wake_word_loop,
        args=(stop_event,),
        daemon=True,
        name='WakeWordEngine',
    )
    thread.start()
    return thread, stop_event
