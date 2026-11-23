"""Productivity commands: search, apps, math, jokes, file/folder creation."""

from __future__ import annotations

import datetime
import logging
import os
import platform
import re
import webbrowser

from shared import config
from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)


def open_notepad(query: str) -> CommandResult:
    """Open the Windows Notepad application."""
    try:
        os.startfile("notepad.exe")
        return CommandResult(
            text="Opening Notepad.", severity=Severity.SUCCESS, source="productivity"
        )
    except Exception as exc:
        logger.error("Notepad launch error: %s", exc)
        return CommandResult(
            text="Sorry, I could not open Notepad.",
            severity=Severity.ERROR,
            source="productivity",
        )


def open_youtube(query: str) -> CommandResult:
    """Open YouTube in the default web browser."""
    try:
        webbrowser.open("https://www.youtube.com")
        return CommandResult(
            text="Opening YouTube.", severity=Severity.SUCCESS, source="productivity"
        )
    except Exception as exc:
        logger.error("YouTube open error: %s", exc)
        return CommandResult(
            text="Sorry, I could not open YouTube.",
            severity=Severity.ERROR,
            source="productivity",
        )


def open_google(query: str) -> CommandResult:
    """Open Google in the default web browser."""
    try:
        webbrowser.open("https://www.google.com")
        return CommandResult(
            text="Opening Google.", severity=Severity.SUCCESS, source="productivity"
        )
    except Exception as exc:
        logger.error("Google open error: %s", exc)
        return CommandResult(
            text="Sorry, I could not open Google.",
            severity=Severity.ERROR,
            source="productivity",
        )


def calculate(query: str) -> CommandResult:
    """Perform basic arithmetic from the query."""
    query_lower = query.lower()
    numbers = [int(n) for n in re.findall(r"\d+", query_lower)]

    if len(numbers) < 2:
        return CommandResult(
            text="I need at least two numbers to calculate.",
            severity=Severity.WARNING,
            source="productivity",
        )

    try:
        if "plus" in query_lower or "add" in query_lower:
            result = sum(numbers)
            return CommandResult(text=f"The answer is {result}.", source="productivity")

        elif "minus" in query_lower or "subtract" in query_lower:
            result = numbers[0]
            for n in numbers[1:]:
                result -= n
            return CommandResult(text=f"The answer is {result}.", source="productivity")

        elif "multiply" in query_lower or "times" in query_lower:
            result = 1
            for n in numbers:
                result *= n
            return CommandResult(text=f"The answer is {result}.", source="productivity")

        elif "divide" in query_lower or "divided" in query_lower:
            result = numbers[0]
            for n in numbers[1:]:
                if n == 0:
                    return CommandResult(
                        text="I cannot divide by zero.",
                        severity=Severity.ERROR,
                        source="productivity",
                    )
                result /= n
            if result == int(result):
                result = int(result)
            return CommandResult(text=f"The answer is {result}.", source="productivity")

        else:
            return CommandResult(
                text="I could not determine the operation. Please say plus, minus, multiply, or divide.",
                severity=Severity.WARNING,
                source="productivity",
            )

    except Exception as exc:
        logger.error("Calculation error: %s", exc)
        return CommandResult(
            text="Sorry, I encountered an error during calculation.",
            severity=Severity.ERROR,
            source="productivity",
        )


def tell_joke(query: str) -> CommandResult:
    """Return a random programming joke."""
    try:
        import pyjokes

        joke = pyjokes.get_joke()
        return CommandResult(text=joke, source="productivity")
    except ImportError:
        logger.error("pyjokes is not installed.")
        return CommandResult(
            text="The jokes library is not installed.",
            severity=Severity.ERROR,
            source="productivity",
        )
    except Exception as exc:
        logger.error("Joke error: %s", exc)
        return CommandResult(
            text="Sorry, I could not come up with a joke right now.",
            severity=Severity.ERROR,
            source="productivity",
        )


def create_file(query: str) -> CommandResult:
    """Create an empty file, optionally on the desktop."""
    query_lower = query.lower()

    try:
        if "file" in query_lower:
            filename = query_lower.split("file", 1)[1].strip()
        else:
            filename = ""

        for prefix in ("called", "named"):
            if filename.startswith(prefix):
                filename = filename[len(prefix) :].strip()

        on_desktop = "on desktop" in filename
        filename = filename.replace("on desktop", "").strip()

        if not filename:
            return CommandResult(
                text="Please specify a filename.",
                severity=Severity.WARNING,
                source="productivity",
            )

        if on_desktop:
            filepath = os.path.join(config.DESKTOP_PATH, filename)
        else:
            filepath = os.path.join(os.getcwd(), filename)

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8"):
            pass

        logger.info("Created file: %s", filepath)
        return CommandResult(
            text=f"File {filename} created successfully.",
            severity=Severity.SUCCESS,
            source="productivity",
        )

    except Exception as exc:
        logger.error("File creation error: %s", exc)
        return CommandResult(
            text="Sorry, I could not create the file.",
            severity=Severity.ERROR,
            source="productivity",
        )


def create_folder(query: str) -> CommandResult:
    """Create a new folder/directory, optionally on the desktop."""
    query_lower = query.lower()

    try:
        folder_name = ""
        for keyword in ("directory", "folder", "dir"):
            if keyword in query_lower:
                folder_name = query_lower.split(keyword, 1)[1].strip()
                break

        for prefix in ("called", "named"):
            if folder_name.startswith(prefix):
                folder_name = folder_name[len(prefix) :].strip()

        on_desktop = "on desktop" in folder_name
        folder_name = folder_name.replace("on desktop", "").strip()

        if not folder_name:
            return CommandResult(
                text="Please specify a folder name.",
                severity=Severity.WARNING,
                source="productivity",
            )

        if on_desktop:
            folderpath = os.path.join(config.DESKTOP_PATH, folder_name)
        else:
            folderpath = os.path.join(os.getcwd(), folder_name)

        os.makedirs(folderpath, exist_ok=True)

        logger.info("Created folder: %s", folderpath)
        return CommandResult(
            text=f"Folder {folder_name} created successfully.",
            severity=Severity.SUCCESS,
            source="productivity",
        )

    except Exception as exc:
        logger.error("Folder creation error: %s", exc)
        return CommandResult(
            text="Sorry, I could not create the folder.",
            severity=Severity.ERROR,
            source="productivity",
        )


def system_status(query: str) -> CommandResult:
    """Return the operating system name and current date/time."""
    try:
        os_name = platform.system()
        now = datetime.datetime.now().strftime("%B %d, %Y %I:%M %p")
        text = f"Running on {os_name}. Current date and time is {now}."
        return CommandResult(text=text, source="productivity")
    except Exception as exc:
        logger.error("System status error: %s", exc)
        return CommandResult(
            text="Sorry, I could not retrieve system status.",
            severity=Severity.ERROR,
            source="productivity",
        )
