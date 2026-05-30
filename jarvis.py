#!/usr/bin/env python3
"""JARVIS 2.0 — Modular Desktop Agent.

A production-grade, voice-controlled desktop assistant with:
- Wake-word activation (Porcupine)
- Centralized command routing (DRY architecture)
- Background monitoring (battery, security)
- Local LLM fallback (Ollama)

Usage:
    python run.py --cli
"""
from __future__ import annotations

import datetime
import logging
import sys

# ─── Project Imports ─────────────────────────────────────────────────
from shared import config
from shared.logging_config import configure_logging
from shared.schemas import CommandResult
from backend.core.tts import speak
from backend.core.stt import take_command
from backend.core.router import process_command
from backend.background.battery_monitor import start_battery_monitor
from backend.background.face_monitor import start_face_monitor

logger = logging.getLogger('jarvis')


def _get_greeting() -> str:
    """Return a time-appropriate greeting string."""
    hour = datetime.datetime.now().hour
    if hour < 12:
        return 'Good Morning'
    elif hour < 18:
        return 'Good Afternoon'
    return 'Good Evening'


def _execute_and_speak(query: str) -> bool:
    """Execute command, speak the result, and return True if we should continue."""
    result: CommandResult = process_command(query)
    if result.text:
        speak(result.text)
    return result.continue_loop


def _run_demo_mode() -> None:
    """Text-input loop for testing without a microphone."""
    print('\n--- DEMO MODE (Text Input) ---\n')
    while True:
        try:
            user_input = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            speak('Session ended.')
            break
        if not user_input:
            continue
        if not _execute_and_speak(user_input):
            break


def _run_voice_mode() -> None:
    """Continuous voice listening mode (legacy, no wake word)."""
    print('\n--- VOICE MODE ---\n')
    speak('Voice mode activated. What can I do for you, Boss?')
    while True:
        query = take_command()
        if query == 'None':
            continue
        if not _execute_and_speak(query):
            break


def _run_wake_word_mode() -> None:
    """Wake-word activated mode using Porcupine."""
    from backend.modules.wake_word import listen_for_wake_word

    print('\n--- WAKE WORD MODE ---\n')
    speak('Wake word mode activated. Say the wake word to get my attention.')

    while True:
        if not listen_for_wake_word():
            speak('Wake word engine failed. Falling back to voice mode.')
            _run_voice_mode()
            return

        speak('Yes, Boss?')
        query = take_command()

        if query == 'None':
            continue
        if not _execute_and_speak(query):
            break


def main() -> None:
    """Application entry point — initializes subsystems and runs the main loop."""
    configure_logging()
    
    print('\n' + '=' * 60)
    print('  JARVIS 2.0 — Modular Desktop Agent CLI')
    print('=' * 60 + '\n')

    greeting = _get_greeting()
    speak(f'Initializing JARVIS... {greeting}, Boss! What can I do for you?')

    # ── Launch background daemon threads ──────────────────────────
    battery_thread, battery_stop = start_battery_monitor()
    face_thread, face_stop = start_face_monitor()

    # ── Mode Selection ────────────────────────────────────────────
    print('Available modes:')
    print('  [1] demo  — Text input (no microphone needed)')
    print('  [2] voice — Continuous listening')
    print('  [3] wake  — Wake-word activated (requires Porcupine key)\n')

    try:
        choice = input('Enter mode (demo/voice/wake): ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = 'demo'

    mode_map = {
        'demo': _run_demo_mode,
        '1': _run_demo_mode,
        'voice': _run_voice_mode,
        '2': _run_voice_mode,
        'wake': _run_wake_word_mode,
        '3': _run_wake_word_mode,
    }

    runner = mode_map.get(choice, _run_demo_mode)

    try:
        runner()
    except KeyboardInterrupt:
        speak('Session interrupted.')
    finally:
        # ── Graceful shutdown ─────────────────────────────────────
        logger.info('Shutting down background threads...')
        if battery_stop:
            battery_stop.set()
        if face_stop:
            face_stop.set()
        logger.info('JARVIS shutdown complete.')


if __name__ == '__main__':
    main()
