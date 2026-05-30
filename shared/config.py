"""Unified JARVIS configuration — shared by backend and frontend.

Loads sensitive values from a `.env` file if present, with safe fallbacks.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; fall back to hardcoded defaults.

# ─── Paths ───────────────────────────────────────────────────────────
DESKTOP_PATH: str = os.path.join(os.path.expanduser("~"), "Desktop")
NOTES_FILE: str = os.path.join(DESKTOP_PATH, "notes.txt")

# ─── TTS Engine ──────────────────────────────────────────────────────
TTS_RATE: int = 150
TTS_VOICE_INDEX: int = 0  # 0 = male (David), 1 = female (Zira) on Windows

# ─── Weather API ─────────────────────────────────────────────────────
WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "YOUR_API_KEY")
WEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5/weather"

# ─── Porcupine Wake Word ─────────────────────────────────────────────
PORCUPINE_ACCESS_KEY: str = os.getenv("PORCUPINE_ACCESS_KEY", "YOUR_PORCUPINE_ACCESS_KEY")
PORCUPINE_KEYWORDS: list[str] = ["computer"]

# ─── Ollama LLM ──────────────────────────────────────────────────────
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT: int = 30
LLM_MAX_RESPONSE_LENGTH: int = 500

# ─── Security (Face Detection Auto-Lock) ─────────────────────────────
SECURITY_AUTOLOCK_ENABLED: bool = False
SECURITY_FACE_TIMEOUT: int = 120
SECURITY_CHECK_INTERVAL: int = 15

# ─── Battery Monitor ─────────────────────────────────────────────────
BATTERY_LOW_THRESHOLD: int = 20
BATTERY_CHECK_INTERVAL: int = 60
