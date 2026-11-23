# JARVIS 2.0 — Plugin Development Guide

## Overview
JARVIS uses a **zero-coupling, convention-based plugin system**. Drop a `.py` file
into the `plugins/` directory and JARVIS will automatically discover and load it
on startup — no edits to `router.py` or any core file required.

## Plugin Contract
Every valid plugin **must** expose these module-level attributes:

```python
PLUGIN_NAME: str        # e.g. "weather_extended"
PLUGIN_VERSION: str     # semver e.g. "1.0.0"
PLUGIN_AUTHOR: str      # e.g. "Krishna Sarathe"
COMMANDS: list[tuple]   # list of (predicate_fn, handler_fn, description)
```

### Optional Lifecycle Hooks
```python
def on_load() -> None:   # Called once when the plugin is loaded (setup/validation)
def on_unload() -> None: # Called on graceful JARVIS shutdown (cleanup)
```

## Command Tuple Structure
Each entry in `COMMANDS` is a 3-tuple:

| Index | Type                              | Purpose                                   |
|-------|-----------------------------------|-------------------------------------------|
| 0     | `Callable[[str], bool]`           | Predicate — returns True if this plugin handles the query |
| 1     | `Callable[[str], CommandResult]`  | Handler — executes and returns a result   |
| 2     | `str`                             | Human-readable description                |

## Available Imports
Plugins **can** import from:
- `shared.schemas` — `CommandResult`, `Severity`, `JarvisEvent`
- `shared.event_bus` — `push_event()`
- `shared.config` — configuration constants

Plugins **must NOT** import from:
- `backend.core.*` — this creates circular dependencies and will break the system

## Minimal Working Template
```python
"""My custom plugin for JARVIS."""
from shared.schemas import CommandResult, Severity

PLUGIN_NAME = "my_plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "Your Name"

def _handle_hello(query: str) -> CommandResult:
    return CommandResult(
        text="Hello from my plugin!",
        severity=Severity.SUCCESS,
        source=PLUGIN_NAME,
    )

COMMANDS = [
    (lambda q: "hello plugin" in q, _handle_hello, "Responds to hello plugin"),
]
```

## Tips
- Plugin commands get **priority** over built-in commands in the router.
- If `on_load()` raises an exception, the plugin is skipped (JARVIS still starts).
- Duplicate `PLUGIN_NAME` values are logged as warnings and skipped.
- Use `python run.py --cli` and type `plugin status` to see all loaded plugins at runtime.
