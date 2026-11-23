from __future__ import annotations

import logging
from typing import Callable

from backend.modules import (
    automation,
    diagnostics,
    file_intel,
    memory,
    productivity,
    system_utils,
    web_services,
)
from backend.core.llm_fallback import ask_llm
from shared.plugin_registry import PluginRegistry
from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────
_EXIT_WORDS: set[str] = {
    "stop",
    "exit",
    "quit",
    "goodbye",
    "bye",
    "shutdown",
    "terminate",
    "stops",
    "exits",
}

_MATH_OPS: set[str] = {"plus", "minus", "multiply", "times", "divide", "divided"}

_CREATE_WORDS: set[str] = {"create", "make", "new", "generate"}

_FOLDER_WORDS: set[str] = {"folder", "dir", "directory"}


def _wants_exit(q: str) -> bool:
    return any(w in q for w in _EXIT_WORDS)


def _has_math(q: str) -> bool:
    return any(op in q for op in _MATH_OPS)


def _wants_create(q: str) -> bool:
    return any(w in q for w in _CREATE_WORDS)


def _wants_folder(q: str) -> bool:
    return any(w in q for w in _FOLDER_WORDS)


# ─── Command Map ─────────────────────────────────────────────────────
# Each entry: (trigger_predicate, handler_function)
# Order matters: first match wins. More specific patterns go first.
_COMMAND_MAP: list[tuple[Callable[[str], bool], Callable[[str], CommandResult]]] = [
    # ── Navigation / Exit ─────────────────────────────────────────
    (_wants_exit, lambda q: _handle_exit(q)),
    # ── System Utilities ──────────────────────────────────────────
    (
        lambda q: "screenshot" in q or "screen capture" in q,
        system_utils.take_screenshot,
    ),
    (lambda q: "note" in q or "dictation" in q, system_utils.take_note),
    (lambda q: "battery" in q or "power" in q, system_utils.check_battery),
    (lambda q: q.startswith("play "), system_utils.play_youtube),
    (
        lambda q: "google search" in q or "search google" in q,
        system_utils.google_search,
    ),
    # ── Web & API Services ────────────────────────────────────────
    (lambda q: "weather" in q or "temperature" in q, web_services.get_weather),
    (lambda q: "wikipedia" in q, web_services.wikipedia_search),
    # ── Productivity (migrated) ───────────────────────────────────
    (lambda q: "open notepad" in q, productivity.open_notepad),
    (lambda q: "open youtube" in q, productivity.open_youtube),
    (lambda q: "open google" in q, productivity.open_google),
    (lambda q: _has_math(q), productivity.calculate),
    (lambda q: "joke" in q, productivity.tell_joke),
    (lambda q: "file" in q and _wants_create(q), productivity.create_file),
    (lambda q: _wants_folder(q) and _wants_create(q), productivity.create_folder),
    (lambda q: "system status" in q, productivity.system_status),
    # ── Date & Time (placed after more-specific matches) ──────────
    (lambda q: "time" in q or "date" in q, system_utils.tell_datetime),
    # ── Cognitive Intelligence ────────────────────────────────────
    (lambda q: "remember that " in q or "memorize " in q, memory.remember_command),
    (lambda q: "recall " in q or "do you remember " in q, memory.recall_command),
    (lambda q: "memory stats" in q, memory.memory_stats_command),
    (lambda q: "system scan" in q or "diagnostics" in q, diagnostics.system_scan),
    (lambda q: "top processes" in q, diagnostics.top_processes),
    (lambda q: "network check" in q, diagnostics.network_check),
    (lambda q: "remind me " in q or "set a reminder" in q, automation.set_reminder),
    (lambda q: "list reminders" in q, automation.list_reminders),
    (lambda q: "cancel reminder" in q, automation.cancel_reminder),
    (lambda q: " and then " in q or " then " in q, automation.chain_commands),
    (lambda q: "find files named " in q or "search for " in q, file_intel.find_files),
    (lambda q: "largest files" in q, file_intel.largest_files),
    (lambda q: "recent files" in q, file_intel.recent_files),
]


def _handle_exit(query: str) -> CommandResult:
    """Handle exit commands by speaking a farewell."""
    return CommandResult(
        text="Goodbye! Have a great day, Boss.",
        continue_loop=False,
        severity=Severity.INFO,
        source="router",
    )


def _handle_plugin_status(query: str) -> CommandResult:
    """Built-in command: list all loaded plugins and their metadata."""
    registry = PluginRegistry.get_instance()
    plugins = registry.get_loaded_plugins()

    if not plugins:
        return CommandResult(
            text="No plugins are currently loaded.",
            severity=Severity.INFO,
            source="router",
        )

    lines = [f"Loaded Plugins ({len(plugins)}):\n"]
    for p in plugins:
        lines.append(
            f"  • {p['name']} v{p['version']} by {p['author']} "
            f"— {p['command_count']} command(s)"
        )

    return CommandResult(
        text="\n".join(lines),
        severity=Severity.INFO,
        source="router",
    )


def process_command(query: str) -> CommandResult:
    """Central command router — the single entry point for all user queries.

    Iterates the command map for the first matching trigger predicate
    and dispatches to its handler. Falls back to the local LLM if no
    hardcoded command matches.

    Args:
        query: Raw user query string (will be lowercased internally).

    Returns:
        Structured CommandResult.
    """
    query = query.lower().strip()
    if not query:
        return CommandResult(text="", continue_loop=True, source="router")

    logger.info('Routing query: "%s"', query)

    from backend.modules.memory import get_engine

    engine = get_engine()

    # ── Built-in: Plugin Status ──────────────────────────────────
    if "plugin status" in query or "list plugins" in query:
        result = _handle_plugin_status(query)
        engine.log_conversation(query, result.text, source=result.source)
        return result

    # ── Phase 1: Check plugin commands (priority over built-ins) ─
    registry = PluginRegistry.get_instance()
    for predicate, handler, _ in registry.get_all_commands():
        if predicate(query):
            try:
                result = handler(query)
                engine.log_conversation(query, result.text, source=result.source)
                return result
            except Exception as exc:
                logger.exception(
                    'Plugin handler crashed for query "%s": %s', query, exc
                )
                return CommandResult(
                    text="A plugin encountered an error while processing that command.",
                    severity=Severity.ERROR,
                    source="router",
                )

    # ── Phase 2: Check built-in command map ──────────────────────
    for trigger, handler in _COMMAND_MAP:
        if trigger(query):
            try:
                result = handler(query)
                engine.log_conversation(query, result.text, source=result.source)
                return result
            except Exception as exc:
                # Absolute last-resort catch — a handler should never
                # propagate an exception, but if it does, log and continue.
                logger.exception('Handler crashed for query "%s": %s', query, exc)
                return CommandResult(
                    text="Something went wrong while processing that command.",
                    severity=Severity.ERROR,
                    source="router",
                )

    # No hardcoded command matched → fall back to local LLM.
    logger.info("No command matched — falling back to LLM.")
    result = ask_llm(query)
    engine.log_conversation(query, result.text, source=result.source)
    return result
