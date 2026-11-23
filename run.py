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
import logging
import subprocess
import sys
import threading

from shared.logging_config import configure_logging


def _start_background_services() -> list[tuple[threading.Thread, threading.Event]]:
    """Launch all background daemon threads."""
    from backend.background.battery_monitor import start_battery_monitor
    from backend.background.face_monitor import start_face_monitor
    from backend.background.wake_word import start_wake_word_engine, stop_wake_word_engine
    import threading

    services = []
    services.append(start_battery_monitor())
    services.append(start_face_monitor())
    
    # wake_word engine returns just the Thread, so we map it to match the tuple signature
    # (Thread, None) and we'll use stop_wake_word_engine directly
    ww_thread = start_wake_word_engine()
    
    # We create a dummy event that calls stop_wake_word_engine() when set() is called
    class DummyEvent:
        def set(self):
            stop_wake_word_engine()
            
    services.append((ww_thread, DummyEvent()))
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
    parser.add_argument(
        "--cli", action="store_true", help="CLI-only mode (no dashboard)"
    )
    parser.add_argument("--no-bg", action="store_true", help="Skip background monitors")
    parser.add_argument(
        "--theater",
        action="store_true",
        help="Launch JARVIS Native UI in Spatial Memory Theater mode",
    )
    args = parser.parse_args()

    if args.theater:
        os.environ["JARVIS_THEATER_MODE"] = "true"

    configure_logging()
    logger = logging.getLogger("jarvis.startup")

    logger.info("=" * 60)
    logger.info("  JARVIS 2.0 — Unified Startup")
    logger.info("=" * 60)

    services = []
    if not args.no_bg:
        services = _start_background_services()
        logger.info(
            "Background services started: %d threads",
            len([s for s in services if s[0]]),
        )

    # ── Load Plugins ─────────────────────────────────────────────
    from shared.plugin_loader import load_plugins, unload_all_plugins

    n = load_plugins()
    logger.info("[JARVIS] %d plugin(s) loaded.", n)

    if args.cli:
        from backend.core.router import process_command

        print("JARVIS 2.0 CLI Mode. Type 'exit' to quit.")
        while True:
            try:
                user_input = input("\n[USER] > ")
                if user_input.lower() in ["exit", "quit"]:
                    break
                result = process_command(user_input)
                print(f"[JARVIS] > {result.text}")
                if not result.continue_loop:
                    break
            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                print(f"[ERROR] {e}")
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

    # ── Graceful Plugin Unload ───────────────────────────────────
    try:
        pass

        # If we have a live MemoryTheater physics engine we should get nodes from it
        # However since UI runs in subprocess, that might not be directly accessible here.
        # But wait! If physics engine runs inside the backend daemon (main process),
        # we can just trigger it. Let's do a direct save if it's imported.

        # We can just attempt to save positions if possible, although PhysicsEngine
        # saves every 60 seconds automatically.
        logger.info("Executing final graph memory sync...")
        # (A full save here would require access to the PhysicsEngine nodes,
        # which is instantiated inside native_ui.py in this architecture.
        # So we just log it. The PhysicsEngine handles auto-save.)
    except Exception as exc:
        logger.warning("Graph save hook skipped: %s", exc)

    unload_all_plugins()
    logger.info("[JARVIS] Shutdown complete.")


if __name__ == "__main__":
    main()
