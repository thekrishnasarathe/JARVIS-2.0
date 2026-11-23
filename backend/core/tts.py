from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading
import queue
import uuid

from shared import config

logger = logging.getLogger(__name__)

# ─── Text Cleaning ───────────────────────────────────────────────────
# Strip non-ASCII, markdown, and intelligently trim long list-style
# responses so JARVIS speaks naturally like a real assistant.

def _clean_for_speech(text: str) -> str:
    """Clean text for natural TTS.  Smart about lists vs. conversation."""
    
    # 1. Detect if this is a list-style response BEFORE stripping characters
    lines = text.strip().split("\n")
    bullet_lines = [
        l for l in lines
        if re.match(r"^\s*[\-\*\u2022]\s+", l) or re.match(r"^\s*\d+[\.\)]\s+", l)
    ]
    is_list = len(bullet_lines) >= 3

    if is_list:
        # Extract the intro (non-bullet lines before the list)
        intro_parts = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^\s*[\-\*\u2022]\s+", line) or re.match(r"^\s*\d+[\.\)]\s+", line):
                break
            intro_parts.append(stripped)

        # Build the spoken version: intro + count summary
        intro = ". ".join(intro_parts) if intro_parts else ""

        # Extract just the heading/key phrase from each bullet
        headings = []
        for bl in bullet_lines[:6]:  # Max 6 key headings
            clean_bl = re.sub(r"^\s*[\-\*\u2022\d+\.\)]+\s*", "", bl).strip()
            # Clean markdown out of the heading before splitting
            clean_bl = re.sub(r"\*+", "", clean_bl)
            # Split on " - " or ": " or " \u2014 "
            heading = re.split(r"\s+[\-\u2014]\s+|:\s+", clean_bl)[0].strip()
            if heading and len(heading) < 50:
                headings.append(heading)

        if intro and headings:
            text = f"{intro}, including {', '.join(headings)}"
            if len(bullet_lines) > 6:
                text += f", and {len(bullet_lines) - 6} more"
            text += "."
        elif intro:
            text = f"{intro}. I've listed {len(bullet_lines)} items on screen for you."
        else:
            text = f"Here are {len(bullet_lines)} items. Check the screen for the full list."
    else:
        # Regular conversational text — clean up and speak fully
        text = re.sub(r"^[\-\*\u2022]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n+", ". ", text)

    # 2. Now run the aggressive cleaning on the generated spoken text
    # Remove all non-ASCII characters (catches ALL emojis and symbols)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Remove markdown-style formatting
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"`+", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Final cleanup
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\.\s*\.", ".", text)

    # 3. Safety net: If the remaining text is still extremely long, trim it
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) > 4:
        text = " ".join(sentences[:4])
        if not text.endswith("."):
            text += "."

    return text.strip()


def _pick_rate(text: str) -> str:
    """Dynamically pick speech rate based on text length."""
    length = len(text)
    if length < 80:
        return "-5%"
    elif length < 200:
        return "+5%"
    elif length < 400:
        return "+15%"
    else:
        return "+25%"


# ─── Interruption ────────────────────────────────────────────────────
_interrupt = threading.Event()

# ─── TTS Worker ──────────────────────────────────────────────────────
_tts_queue: queue.Queue[str | None] = queue.Queue()

_TMP_DIR = os.path.join(tempfile.gettempdir(), "jarvis_tts")
os.makedirs(_TMP_DIR, exist_ok=True)

_pygame_ready = False


def _ensure_pygame():
    global _pygame_ready
    if not _pygame_ready:
        import pygame
        pygame.mixer.init()
        _pygame_ready = True


def _speak_edge(text: str) -> bool:
    """Speak using edge-tts + pygame mixer."""
    try:
        import edge_tts
        import pygame
    except ImportError:
        return False

    audio_path = os.path.join(_TMP_DIR, f"resp_{uuid.uuid4().hex}.mp3")

    try:
        rate = _pick_rate(text)
        communicate = edge_tts.Communicate(
            text,
            voice="en-US-AndrewNeural",
            rate=rate,
            pitch="-5Hz",
        )
        # Fresh event loop every call — safest on Windows.
        asyncio.run(communicate.save(audio_path))

        _ensure_pygame()

        if _interrupt.is_set():
            return True

        # Unload previous track to release file handles
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if _interrupt.is_set():
                pygame.mixer.music.stop()
                break
            pygame.time.wait(50)

        # Release file handle and clean up
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        try:
            os.remove(audio_path)
        except OSError:
            pass

        return True
    except Exception as exc:
        logger.error("edge-tts error: %s", exc)
        # Clean up on failure
        try:
            os.remove(audio_path)
        except OSError:
            pass
        return False


def _speak_pyttsx3(text: str) -> bool:
    """Fallback: speak using pyttsx3 SAPI5."""
    try:
        import pyttsx3
    except ImportError:
        return False

    try:
        engine = pyttsx3.init("sapi5")
        engine.setProperty("rate", config.TTS_RATE)
        voices = engine.getProperty("voices")
        if voices and len(voices) > config.TTS_VOICE_INDEX:
            engine.setProperty("voice", voices[config.TTS_VOICE_INDEX].id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception as exc:
        logger.error("pyttsx3 error: %s", exc)
        return False


def _tts_worker() -> None:
    """Background TTS loop. Never dies — all errors are caught."""
    logger.info("TTS worker thread started.")
    while True:
        try:
            text = _tts_queue.get()
            if text is None:
                break

            _interrupt.clear()

            if not _speak_edge(text):
                logger.warning("edge-tts failed, trying pyttsx3 fallback")
                _speak_pyttsx3(text)

        except Exception as exc:
            # Catch-all: the worker must NEVER die
            logger.error("TTS worker unexpected error: %s", exc)


_worker = threading.Thread(target=_tts_worker, daemon=True, name="tts-worker")
_worker.start()


def speak(text: str) -> None:
    """Convert text to audible speech.

    Thread-safe. If JARVIS is currently speaking, interrupts and
    speaks the new text instead.
    """
    if not text:
        return
    try:
        print(f"JARVIS: {text.encode('ascii', 'ignore').decode('ascii')}")
    except Exception:
        pass

    clean = _clean_for_speech(text)
    if not clean:
        return

    # Interrupt current speech
    _interrupt.set()

    # Drain any stale queued messages
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break

    _tts_queue.put(clean)


def stop_speaking() -> None:
    """Immediately silence JARVIS."""
    _interrupt.set()
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break
