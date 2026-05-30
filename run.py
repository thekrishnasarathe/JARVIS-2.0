"""JARVIS 2.0 — Unified Startup Orchestrator.

Launches both backend background services and the Native 3D frontend
in a single coordinated process.

Usage:
    python run.py              # Start the full stack (frontend + background services)
    python run.py --cli        # Start CLI-only mode (no GUI)
    python run.py --no-bg      # Start GUI without background monitors
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import signal
import threading
import logging

from shared.logging_config import configure_logging
from shared import config


def _start_background_services() -> list[tuple[threading.Thread, threading.Event]]:
    """Launch all background daemon threads."""
    from backend.background.battery_monitor import start_battery_monitor
    from backend.background.face_monitor import start_face_monitor
    from backend.background.wake_word import start_wake_word_engine

    services = []
    services.append(start_battery_monitor())
    services.append(start_face_monitor())
    services.append(start_wake_word_engine())
    return services


import os
import pathlib

def get_python_exe() -> str:
    """Find the correct Python executable from local venv."""
    if sys.prefix != sys.base_prefix:
        return sys.executable
    
    # Try common local venv paths
    base = pathlib.Path(__file__).parent
    for venv_name in [".venv", "venv"]:
        if os.name == "nt":
            exe = base / venv_name / "Scripts" / "python.exe"
        else:
            exe = base / venv_name / "bin" / "python"
        if exe.exists():
            return str(exe)
    
    return sys.executable

def _run_native_ui() -> None:
    """Start the Native 3D JARVIS Dashboard (PyQt6 + PyVista)."""
    exe = get_python_exe()
    # Start the PyQt6 application
    subprocess.run(
        [exe, "-m", "frontend.native_ui"],
        cwd=".",
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS 2.0 Startup Orchestrator")
    parser.add_argument("--cli", action="store_true", help="CLI-only mode (no dashboard)")
    parser.add_argument("--no-bg", action="store_true", help="Skip background monitors")
    args = parser.parse_args()

    configure_logging()
    logger = logging.getLogger("jarvis.startup")

    logger.info("=" * 60)
    logger.info("  JARVIS 2.0 — Unified Startup")
    logger.info("=" * 60)

    services = []
    if not args.no_bg:
        services = _start_background_services()
        logger.info("Background services started: %d threads", len([s for s in services if s[0]]))

    if args.cli:
        from jarvis import main as cli_main
        cli_main()
    else:
        try:
            _run_native_ui()
        except KeyboardInterrupt:
            logger.info("Shutting down UI...")
        finally:
            if not args.no_bg:
                logger.info("Shutting down background services...")
                for thread, stop_event in services:
                    if stop_event:
                        stop_event.set()


if __name__ == "__main__":
    main()
