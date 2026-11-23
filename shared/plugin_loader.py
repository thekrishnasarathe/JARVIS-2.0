"""Dynamic plugin loader — discovers and loads *.py files from the plugins dir.

Uses importlib to load modules at runtime without modifying sys.path.
Validates each module against the plugin contract before registering.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from shared import config
from shared.plugin_registry import PluginRegistry

logger = logging.getLogger(__name__)

_REQUIRED_ATTRS = ("PLUGIN_NAME", "PLUGIN_VERSION", "COMMANDS")


def load_plugins(plugin_dir: str | None = None) -> int:
    """Scan *plugin_dir* for valid plugin files and register them.

    Args:
        plugin_dir: Absolute or relative path to the plugins directory.
                    Defaults to ``config.PLUGIN_DIR``.

    Returns:
        Number of plugins successfully loaded.
    """
    plugin_dir = plugin_dir or config.PLUGIN_DIR

    # Resolve relative paths against the project root
    base = Path(__file__).resolve().parent.parent
    plugin_path = (base / plugin_dir).resolve()

    if not plugin_path.is_dir():
        logger.warning("[PLUGIN] Plugin directory does not exist: %s", plugin_path)
        return 0

    registry = PluginRegistry.get_instance()
    loaded = 0

    for entry in sorted(plugin_path.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".py":
            continue
        if entry.name.startswith("_"):
            continue

        module_name = f"plugins.{entry.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, str(entry))
            if spec is None or spec.loader is None:
                logger.warning(
                    "[PLUGIN] FAILED: %s — could not create import spec", entry.name
                )
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # ── Validate contract ────────────────────────────────────
            missing = [attr for attr in _REQUIRED_ATTRS if not hasattr(module, attr)]
            if missing:
                logger.warning(
                    "[PLUGIN] FAILED: %s — missing required attributes: %s",
                    entry.name,
                    ", ".join(missing),
                )
                continue

            plugin_name: str = module.PLUGIN_NAME
            plugin_version: str = module.PLUGIN_VERSION
            plugin_author: str = getattr(module, "PLUGIN_AUTHOR", "Unknown")
            commands: list = module.COMMANDS

            # ── Optional on_load() ───────────────────────────────────
            on_load = getattr(module, "on_load", None)
            if callable(on_load):
                try:
                    on_load()
                except Exception as exc:
                    logger.warning(
                        "[PLUGIN] FAILED: %s — on_load() raised: %s",
                        entry.name,
                        exc,
                    )
                    continue

            # ── Register ─────────────────────────────────────────────
            registry.register(
                plugin_name, plugin_version, plugin_author, commands, module
            )
            logger.info(
                "[PLUGIN] Loaded: %s v%s (%d commands)",
                plugin_name,
                plugin_version,
                len(commands),
            )
            loaded += 1

        except Exception as exc:
            logger.warning("[PLUGIN] FAILED: %s — %s", entry.name, exc)

    return loaded


def unload_all_plugins() -> None:
    """Call on_unload() for every loaded plugin, then clear the registry."""
    registry = PluginRegistry.get_instance()

    for info in registry.get_loaded_plugins():
        name = info["name"]
        # Retrieve the actual module to call on_unload
        # We need to access internals here — the registry stores modules
        with registry._lock:
            plugin_data = registry._plugins.get(name)
            if plugin_data:
                module = plugin_data.get("module")
                on_unload = getattr(module, "on_unload", None)
                if callable(on_unload):
                    try:
                        on_unload()
                        logger.info("[PLUGIN] Unloaded: %s", name)
                    except Exception as exc:
                        logger.warning(
                            "[PLUGIN] on_unload() failed for %s: %s", name, exc
                        )

    registry._clear()
    logger.info("[PLUGIN] All plugins unloaded.")
