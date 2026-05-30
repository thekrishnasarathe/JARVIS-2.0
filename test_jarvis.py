"""
JARVIS 2.0 -- Test Suite

Validates the modular architecture by running commands through the
centralized process_command() router in demo mode (no microphone needed).
"""
from __future__ import annotations

import io
import os
import sys

# Force UTF-8 on Windows consoles that default to cp1252.
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

# ─── Core imports ────────────────────────────────────────────────────
from backend.core.tts import speak, engine
from backend.core.router import process_command
from shared.schemas import CommandResult

print("\n" + "=" * 60)
print("  JARVIS 2.0 — FUNCTIONALITY TEST SUITE")
print("=" * 60 + "\n")

# ─── Test Registry ───────────────────────────────────────────────────
# Each test: (description, input_query, expected_continue_loop)
TESTS: list[tuple[str, str, bool]] = [
    ("Voice engine init",            None,                      None),
    ("Time command",                 "what is the time",        True),
    ("Date command",                 "what is the date",        True),
    ("Date + Time command",          "date and time",           True),
    ("Battery check",                "check battery",           True),
    ("Math: addition",               "5 plus 3",               True),
    ("Math: multiplication",         "7 times 6",              True),
    ("Math: division by zero",       "10 divide 0",            True),
    ("Joke",                         "tell me a joke",          True),
    ("System status",                "system status",           True),
    ("Open Google",                  "open google",             True),
    ("LLM fallback (unrecognized)",  "explain quantum physics", True),
    ("Exit command",                 "goodbye",                 False),
]

passed = 0
failed = 0

for i, (desc, query, expected_loop) in enumerate(TESTS, 1):
    try:
        if query is None:
            # Special case: just verify engine initialized.
            rate = engine.getProperty('rate')
            print(f"  [PASS] Test {i:2d}: {desc} (rate={rate} WPM)")
            passed += 1
            continue

        result: CommandResult = process_command(query)

        if result.continue_loop == expected_loop:
            print(f"  [PASS] Test {i:2d}: {desc} -> {result.text[:50]}")
            passed += 1
        else:
            print(f"  [FAIL] Test {i:2d}: {desc} -- expected loop {expected_loop}, got {result.continue_loop}")
            failed += 1

    except Exception as exc:
        print(f"  [FAIL] Test {i:2d}: {desc} -- EXCEPTION: {exc}")
        failed += 1

# ─── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print("=" * 60 + "\n")

sys.exit(0 if failed == 0 else 1)
