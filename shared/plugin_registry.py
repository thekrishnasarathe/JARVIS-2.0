"""Thread-safe Plugin Registry — singleton that tracks all loaded plugins.

Every plugin registers its metadata and command tuples here.
The router queries this registry before checking built-in commands,
giving plugins priority.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Singleton registry for dynamically loaded plugins."""

    _instance: PluginRegistry | None = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        raise RuntimeError(
            "Use PluginRegistry.get_instance() instead of direct construction."
        )

    @classmethod
    def get_instance(cls) -> PluginRegistry:
        with cls._class_lock:
            if cls._instance is None:
                inst = object.__new__(cls)
                inst._plugins: dict[str, dict[str, Any]] = {}
                inst._lock = threading.Lock()
                cls._instance = inst
            return cls._instance

    # ── Mutation ──────────────────────────────────────────────────────

    def register(
        self,
        plugin_name: str,
        version: str,
        author: str,
        commands: list[tuple[Callable, Callable, str]],
        module: Any,
    ) -> None:
        """Register a validated plugin into the registry."""
        with self._lock:
            if plugin_name in self._plugins:
                logger.warning(
                    "[PLUGIN] Duplicate plugin '%s' — skipping.", plugin_name
                )
                return
            self._plugins[plugin_name] = {
                "version": version,
                "author": author,
                "commands": commands,
                "module": module,
            }
            logger.info(
                "[PLUGIN] Registered: %s v%s by %s (%d commands)",
                plugin_name,
                version,
                author,
                len(commands),
            )

    def unregister(self, plugin_name: str) -> bool:
        """Remove a plugin from the registry. Returns True if it existed."""
        with self._lock:
            if plugin_name in self._plugins:
                del self._plugins[plugin_name]
                logger.info("[PLUGIN] Unregistered: %s", plugin_name)
                return True
            return False

    # ── Queries ───────────────────────────────────────────────────────

    def get_all_commands(self) -> list[tuple[Callable, Callable, str]]:
        """Return a flat list of (predicate, handler, description) from all plugins."""
        with self._lock:
            result: list[tuple[Callable, Callable, str]] = []
            for info in self._plugins.values():
                result.extend(info["commands"])
            return result

    def get_loaded_plugins(self) -> list[dict[str, Any]]:
        """Return metadata for every loaded plugin (for status display)."""
        with self._lock:
            return [
                {
                    "name": name,
                    "version": info["version"],
                    "author": info["author"],
                    "command_count": len(info["commands"]),
                }
                for name, info in self._plugins.items()
            ]

    # ── Internals ─────────────────────────────────────────────────────

    def _clear(self) -> None:
        """Clear all plugins (used by unload_all_plugins)."""
        with self._lock:
            self._plugins.clear()
