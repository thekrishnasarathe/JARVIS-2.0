"""JARVIS Smart File Operations module.

File searching, duplicate detection, and size analysis.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import time
from pathlib import Path

from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def _get_common_dirs() -> list[str]:
    home = str(Path.home())
    dirs = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
    ]
    return [d for d in dirs if os.path.exists(d)]


def find_files(query: str) -> CommandResult:
    """Find files by name."""
    search_term = ""
    for prefix in ("find files named ", "find file ", "search for "):
        if prefix in query.lower():
            search_term = query.lower().split(prefix)[1].strip()
            break

    if not search_term:
        return CommandResult(
            text="Please specify what file to search for.",
            severity=Severity.WARNING,
            source="file_intel",
        )

    start_dir = str(Path.home())
    pattern = f"*{search_term}*"

    # Common excludes
    excludes = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "AppData",
        "Local Settings",
    }

    results = []
    start_time = time.time()

    try:
        for root, dirs, files in os.walk(start_dir):
            # Timeout after 10 seconds
            if time.time() - start_time > 10:
                results.append("... (Search timed out, showing partial results)")
                break

            # Filter directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in excludes]

            for f in files:
                if fnmatch.fnmatch(f.lower(), pattern.lower()):
                    filepath = os.path.join(root, f)
                    try:
                        size = os.path.getsize(filepath)
                        results.append((filepath, size))
                    except OSError:
                        pass

                    if len(results) >= 20:
                        break
            if len(results) >= 20:
                break

        if not results:
            return CommandResult(
                text=f"No files found matching '{search_term}'.", source="file_intel"
            )

        report = f"--- FOUND FILES ({len(results)}) ---\n"
        for item in results:
            if isinstance(item, tuple):
                report += f"{item[0]} ({_human_size(item[1])})\n"
            else:
                report += f"{item}\n"

        return CommandResult(text=report.strip(), source="file_intel")

    except Exception as exc:
        logger.error("File search error: %s", exc)
        return CommandResult(
            text=f"Search failed: {exc}", severity=Severity.ERROR, source="file_intel"
        )


def largest_files(query: str) -> CommandResult:
    """Find top 10 largest files in user directories."""
    dirs_to_scan = _get_common_dirs()
    if not dirs_to_scan:
        return CommandResult(
            text="Could not locate common user directories.",
            severity=Severity.ERROR,
            source="file_intel",
        )

    files_with_size = []

    try:
        for scan_dir in dirs_to_scan:
            for root, dirs, files in os.walk(scan_dir):
                for f in files:
                    filepath = os.path.join(root, f)
                    try:
                        size = os.path.getsize(filepath)
                        files_with_size.append((filepath, size))
                    except OSError:
                        pass

        files_with_size.sort(key=lambda x: x[1], reverse=True)

        report = "--- TOP 10 LARGEST FILES ---\n"
        for path, size in files_with_size[:10]:
            report += f"[{_human_size(size):>10}] {path}\n"

        return CommandResult(text=report.strip(), source="file_intel")

    except Exception as exc:
        logger.error("Largest files error: %s", exc)
        return CommandResult(
            text=f"Operation failed: {exc}",
            severity=Severity.ERROR,
            source="file_intel",
        )


def recent_files(query: str) -> CommandResult:
    """Find top 15 recently modified files."""
    dirs_to_scan = _get_common_dirs()
    files_with_mtime = []

    try:
        for scan_dir in dirs_to_scan:
            for root, dirs, files in os.walk(scan_dir):
                for f in files:
                    filepath = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(filepath)
                        files_with_mtime.append((filepath, mtime))
                    except OSError:
                        pass

        files_with_mtime.sort(key=lambda x: x[1], reverse=True)

        report = "--- RECENTLY MODIFIED FILES ---\n"
        import datetime

        for path, mtime in files_with_mtime[:15]:
            dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            report += f"[{dt}] {os.path.basename(path)}\n"

        return CommandResult(text=report.strip(), source="file_intel")

    except Exception as exc:
        return CommandResult(
            text=f"Operation failed: {exc}",
            severity=Severity.ERROR,
            source="file_intel",
        )
