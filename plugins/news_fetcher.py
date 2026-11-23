"""News Fetcher — Demo Plugin #1 for JARVIS 2.0.

Fetches the top 5 BBC News headlines via RSS and returns them as a
formatted numbered list. Uses only xml.etree.ElementTree for parsing.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)

PLUGIN_NAME = "news_fetcher"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "Krishna Sarathe"

_BBC_RSS_URL = "https://feeds.bbcnews.com/news/rss.xml"
_MAX_HEADLINES = 5


def _wants_news(query: str) -> bool:
    triggers = {"news", "headlines", "top stories", "what's happening"}
    return any(t in query for t in triggers)


def _fetch_news(query: str) -> CommandResult:
    """Fetch and format BBC News headlines."""
    try:
        resp = requests.get(_BBC_RSS_URL, timeout=10)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)

        # RSS structure: <rss><channel><item><title>…</title><link>…</link></item>…
        items = root.findall(".//item")

        if not items:
            return CommandResult(
                text="I fetched the BBC RSS feed but found no articles.",
                severity=Severity.WARNING,
                source=PLUGIN_NAME,
            )

        lines = ["Here are the top BBC News headlines:\n"]
        for i, item in enumerate(items[:_MAX_HEADLINES], start=1):
            title_el = item.find("title")
            link_el = item.find("link")
            title = (
                title_el.text.strip()
                if title_el is not None and title_el.text
                else "Untitled"
            )
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            lines.append(f"  {i}. {title}")
            if link:
                lines.append(f"     {link}")

        return CommandResult(
            text="\n".join(lines),
            severity=Severity.INFO,
            source=PLUGIN_NAME,
        )

    except requests.RequestException as exc:
        logger.warning("[PLUGIN:%s] RSS fetch failed: %s", PLUGIN_NAME, exc)
        return CommandResult(
            text=f"Could not fetch news headlines: {exc}",
            severity=Severity.WARNING,
            source=PLUGIN_NAME,
        )
    except ET.ParseError as exc:
        logger.warning("[PLUGIN:%s] RSS XML parse error: %s", PLUGIN_NAME, exc)
        return CommandResult(
            text=f"Failed to parse the BBC RSS feed: {exc}",
            severity=Severity.WARNING,
            source=PLUGIN_NAME,
        )


COMMANDS = [
    (_wants_news, _fetch_news, "Fetches the top 5 BBC News headlines"),
]
