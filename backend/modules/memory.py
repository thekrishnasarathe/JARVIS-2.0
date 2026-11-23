"""JARVIS Eidetic Memory module.

Provides SQLite-backed persistence and TF-IDF semantic search.
"""

from __future__ import annotations

import collections
import datetime
import logging
import math
import os
import re
import sqlite3
import threading
from typing import Any, Counter

from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "jarvis_memory.db",
)
_STOP_WORDS = {
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "ours",
    "ourselves",
    "you",
    "you're",
    "you've",
    "you'll",
    "you'd",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "she's",
    "her",
    "hers",
    "herself",
    "it",
    "it's",
    "its",
    "itself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "that'll",
    "these",
    "those",
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "doing",
    "a",
    "an",
    "the",
    "and",
    "but",
    "if",
    "or",
    "because",
    "as",
    "until",
    "while",
    "of",
    "at",
    "by",
    "for",
    "with",
    "about",
    "against",
    "between",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "to",
    "from",
    "up",
    "down",
    "in",
    "out",
    "on",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "any",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "s",
    "t",
    "can",
    "will",
    "just",
    "don",
    "don't",
    "should",
    "should've",
    "now",
    "d",
    "ll",
    "m",
    "o",
    "re",
    "ve",
    "y",
    "ain",
    "aren",
    "aren't",
    "couldn",
    "couldn't",
    "didn",
    "didn't",
    "doesn",
    "doesn't",
    "hadn",
    "hadn't",
    "hasn",
    "hasn't",
    "haven",
    "haven't",
    "isn",
    "isn't",
    "ma",
    "mightn",
    "mightn't",
    "mustn",
    "mustn't",
    "needn",
    "needn't",
    "shan",
    "shan't",
    "shouldn",
    "shouldn't",
    "wasn",
    "wasn't",
    "weren",
    "weren't",
    "won",
    "won't",
    "wouldn",
    "wouldn't",
    "remember",
    "memorize",
    "that",
    "recall",
    "tell",
}


class MemoryEngine:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MemoryEngine, cls).__new__(cls)
                cls._instance._init_db()
            return cls._instance

    def _init_db(self):
        self.conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    category TEXT,
                    content TEXT,
                    source TEXT,
                    importance INTEGER
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    query TEXT,
                    response TEXT,
                    source TEXT
                )
            """)

    def _tokenize(self, text: str) -> Counter[str]:
        words = re.findall(r"\b\w+\b", text.lower())
        return collections.Counter(w for w in words if w not in _STOP_WORDS)

    def _cosine_similarity(
        self, counter_a: Counter[str], counter_b: Counter[str]
    ) -> float:
        intersection = set(counter_a.keys()) & set(counter_b.keys())
        numerator = sum(counter_a[x] * counter_b[x] for x in intersection)
        sum1 = sum(counter_a[x] ** 2 for x in counter_a.keys())
        sum2 = sum(counter_b[x] ** 2 for x in counter_b.keys())
        denominator = math.sqrt(sum1) * math.sqrt(sum2)
        if not denominator:
            return 0.0
        return float(numerator) / denominator

    def remember(
        self, content: str, category: str = "general", importance: int = 1
    ) -> None:
        now = datetime.datetime.now().isoformat()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO memories (timestamp, category, content, source, importance) VALUES (?, ?, ?, ?, ?)",
                (now, category, content, "user", importance),
            )
            mem_id = cursor.lastrowid

        try:
            from backend.modules.spatial_memory.graph_builder import COLOR_MAP, node_from_new_memory
            from shared.event_bus import push_event
            from shared.schemas import JarvisEvent, Severity

            node = node_from_new_memory(mem_id, content, category, importance)
            color = COLOR_MAP.get(category, COLOR_MAP.get("default", (0.8, 0.8, 0.8)))

            push_event(
                JarvisEvent(
                    message=f"Memory node created: {node.node_id}",
                    severity=Severity.INFO,
                    source="memory",
                    data={
                        "type": "node_event",
                        "node_id": node.node_id,
                        "event_type": "spawn",
                        "color": color,
                    },
                )
            )
        except Exception as e:
            logger.debug(f"Could not spawn node for memory: {e}")

    def log_conversation(
        self, query: str, response: str, source: str = "command"
    ) -> None:
        now = datetime.datetime.now().isoformat()
        with self.conn:
            self.conn.execute(
                "INSERT INTO conversations (timestamp, query, response, source) VALUES (?, ?, ?, ?)",
                (now, query, response, source),
            )

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        c = self.conn.cursor()
        c.execute("SELECT id, timestamp, category, content, importance FROM memories")
        results = []
        for row in c.fetchall():
            mem_tokens = self._tokenize(row["content"])
            score = self._cosine_similarity(query_tokens, mem_tokens)
            if score > 0.05:  # Arbitrary small threshold
                results.append((score, dict(row)))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def get_stats(self) -> dict[str, int]:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM memories")
        mems = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM conversations")
        convs = c.fetchone()[0]
        return {"total_memories": mems, "total_conversations": convs}

    def get_recent_conversations(self, limit: int = 10) -> list[dict[str, str]]:
        c = self.conn.cursor()
        c.execute(
            "SELECT query, response FROM conversations ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        results = []
        for row in c.fetchall():
            results.insert(0, {"query": row["query"], "response": row["response"]})
        return results


_engine = MemoryEngine()


def get_engine() -> MemoryEngine:
    return _engine


def remember_command(query: str) -> CommandResult:
    """Handle 'remember that X' commands."""
    content = query
    for prefix in ("remember that ", "remember ", "memorize that ", "memorize "):
        if query.startswith(prefix):
            content = query[len(prefix) :].strip()
            break

    if not content:
        return CommandResult(
            text="I need something to remember.",
            severity=Severity.WARNING,
            source="memory",
        )

    _engine.remember(content)
    return CommandResult(
        text=f"I have committed to memory: {content}",
        severity=Severity.SUCCESS,
        source="memory",
    )


def recall_command(query: str) -> CommandResult:
    """Handle 'recall X' commands."""
    search_term = query
    for prefix in ("recall ", "what do you remember about ", "do you remember "):
        if query.startswith(prefix):
            search_term = query[len(prefix) :].strip()
            break

    if not search_term:
        return CommandResult(
            text="Please specify what you want me to recall.",
            severity=Severity.WARNING,
            source="memory",
        )

    results = _engine.recall(search_term)
    if not results:
        return CommandResult(
            text=f"I don't have any memories matching '{search_term}'.",
            severity=Severity.INFO,
            source="memory",
        )

    response = "Here is what I remember:\n"
    for r in results:
        date = datetime.datetime.fromisoformat(r["timestamp"]).strftime("%Y-%m-%d")
        response += f"- [{date}] {r['content']}\n"

    return CommandResult(text=response.strip(), source="memory")


def memory_stats_command(query: str) -> CommandResult:
    stats = _engine.get_stats()
    text = f"My eidetic memory currently holds {stats['total_memories']} specific facts and a log of {stats['total_conversations']} conversational interactions."
    return CommandResult(text=text, source="memory")
