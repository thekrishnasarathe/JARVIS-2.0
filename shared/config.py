"""Unified JARVIS configuration — shared by backend and frontend.

Loads sensitive values from a `.env` file if present, with safe fallbacks.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"[FATAL] Missing required environment variable: {key}")
        sys.exit(1)
    return val


# ─── Paths ───────────────────────────────────────────────────────────
DESKTOP_PATH: str = os.path.join(os.path.expanduser("~"), "Desktop")
NOTES_FILE: str = os.path.join(DESKTOP_PATH, "notes.txt")

# ─── TTS Engine ──────────────────────────────────────────────────────
TTS_RATE: int = 150
TTS_VOICE_INDEX: int = 0  # 0 = male (David), 1 = female (Zira) on Windows

# ─── Weather API ─────────────────────────────────────────────────────
WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")
WEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5/weather"

# ─── Wake Word ───────────────────────────────────────────────────────
WAKE_THRESHOLD: float = float(os.getenv("JARVIS_WAKE_THRESHOLD", "0.5"))
WAKE_WORD_MODEL: str = os.getenv("JARVIS_WAKE_WORD_MODEL", "hey_jarvis")

# ─── Ollama LLM ──────────────────────────────────────────────────────
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT: int = 120
LLM_MAX_RESPONSE_LENGTH: int = 500

# ─── Groq API ───────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# ─── Security (Face Detection Auto-Lock) ─────────────────────────────
SECURITY_AUTOLOCK_ENABLED: bool = False
SECURITY_FACE_TIMEOUT: int = 120
SECURITY_CHECK_INTERVAL: int = 15

# ─── Battery Monitor ─────────────────────────────────────────────────
BATTERY_LOW_THRESHOLD: int = 20
BATTERY_CHECK_INTERVAL: int = 60

# ─── Plugin System ───────────────────────────────────────────────────
PLUGIN_DIR: str = os.getenv("JARVIS_PLUGIN_DIR", "plugins")

# ─── Spatial Memory Theater ──────────────────────────────────────────
THEATER_MODE_DEFAULT: bool = os.getenv("JARVIS_THEATER_MODE", "false").lower() == "true"
PHYSICS_TICK_MS: int = int(os.getenv("JARVIS_PHYSICS_TICK_MS", "500"))
GRAPH_SAVE_INTERVAL_S: int = int(os.getenv("JARVIS_GRAPH_SAVE_S", "60"))
SIMILARITY_EDGE_THRESHOLD: float = float(
    os.getenv("JARVIS_SIMILARITY_THRESHOLD", "0.15")
)
