"""Porcupine-based wake word detection engine."""
from __future__ import annotations

import logging
import struct

from shared import config

logger = logging.getLogger(__name__)


def listen_for_wake_word() -> bool:
    """Block until a Porcupine wake word is detected.

    Uses the keywords defined in config.PORCUPINE_KEYWORDS.
    Requires a valid Porcupine access key in config.PORCUPINE_ACCESS_KEY.

    Returns:
        True when a wake word is detected, False on unrecoverable error.
    """
    try:
        import pvporcupine
        import pyaudio
    except ImportError as exc:
        logger.error('Wake word dependencies missing: %s', exc)
        return False

    porcupine = None
    pa = None
    stream = None

    try:
        porcupine = pvporcupine.create(
            access_key=config.PORCUPINE_ACCESS_KEY,
            keywords=config.PORCUPINE_KEYWORDS,
        )

        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length,
        )

        logger.info('Wake word engine active. Listening for: %s', config.PORCUPINE_KEYWORDS)
        print(f'Listening for wake word: {config.PORCUPINE_KEYWORDS}...')

        while True:
            pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm_unpacked = struct.unpack_from('h' * porcupine.frame_length, pcm)
            keyword_index = porcupine.process(pcm_unpacked)

            if keyword_index >= 0:
                detected = config.PORCUPINE_KEYWORDS[keyword_index]
                logger.info('Wake word detected: %s', detected)
                print(f'Wake word "{detected}" detected!')
                return True

    except Exception as exc:
        logger.error('Wake word engine error: %s', exc)
        return False

    finally:
        if stream is not None:
            stream.close()
        if pa is not None:
            pa.terminate()
        if porcupine is not None:
            porcupine.delete()
