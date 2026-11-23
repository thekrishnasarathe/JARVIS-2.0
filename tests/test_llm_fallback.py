from __future__ import annotations

import concurrent.futures
from unittest.mock import MagicMock, patch

from backend.core.llm_fallback import ask_llm
from shared.event_bus import drain_all
from shared.schemas import Severity


def test_ask_llm_groq_success():
    drain_all()

    # Mock the Groq client completions response
    mock_choice = MagicMock()
    mock_choice.message.content = "I am JARVIS. Hello, Boss!"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        return_value=mock_response,
    ) as mock_create:
        result = ask_llm("Hello")

        assert result.text == "I am JARVIS. Hello, Boss!"
        assert result.severity == Severity.INFO
        assert result.source == "groq"

        # Verify call arguments
        mock_create.assert_called_once()

        # Verify event bus entries
        events = drain_all()
        assert len(events) >= 2
        # llm_thinking start
        start_events = [
            e
            for e in events
            if e.data
            and e.data.get("type") == "llm_thinking"
            and e.data.get("state") == "start"
        ]
        assert len(start_events) == 1
        # llm_thinking stop
        stop_events = [
            e
            for e in events
            if e.data
            and e.data.get("type") == "llm_thinking"
            and e.data.get("state") == "stop"
        ]
        assert len(stop_events) == 1


def test_ask_llm_groq_error():
    drain_all()

    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        side_effect=Exception("API connection failed"),
    ) as mock_create:
        result = ask_llm("Hello")

        assert "trouble connecting to my intelligence core" in result.text
        assert result.severity == Severity.ERROR
        assert result.source == "groq"

        # Verify event bus entries
        events = drain_all()
        assert len(events) >= 2
        stop_events = [
            e
            for e in events
            if e.data
            and e.data.get("type") == "llm_thinking"
            and e.data.get("state") == "stop"
        ]
        assert len(stop_events) == 1


def test_ask_llm_groq_history_bounding():
    # Call multiple times to fill conversation history and verify it gets trimmed
    from backend.core.llm_fallback import _conversation_history

    # Reset conversation history
    _conversation_history.clear()
    _conversation_history.append({"role": "system", "content": "System Prompt"})

    mock_choice = MagicMock()
    mock_choice.message.content = "Response"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        return_value=mock_response,
    ):
        # We need to call it 12 times. Each call adds 1 user message and 1 assistant message (2 messages total).
        # System prompt + 12 * 2 = 25 messages.
        # Length threshold in code is 21. If len > 21, it deletes _conversation_history[1:3] (one pair of user/assistant messages).
        for i in range(12):
            ask_llm(f"Query {i}")

        # Ensure length is bounded (should not exceed 21)
        assert len(_conversation_history) <= 21
        # Ensure system prompt is still at index 0
        assert _conversation_history[0]["role"] == "system"


def test_ask_llm_groq_stress_concurrency():
    num_threads = 10

    def worker(idx):
        mock_choice = MagicMock()
        mock_choice.message.content = f"Response {idx}"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch(
            "backend.core.llm_fallback._client.chat.completions.create",
            return_value=mock_response,
        ):
            res = ask_llm(f"Query {idx}")
            return res.text

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == num_threads


def test_ask_llm_groq_empty_response():
    drain_all()

    mock_choice = MagicMock()
    mock_choice.message.content = ""

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        return_value=mock_response,
    ):
        result = ask_llm("Hello")
        assert result.text == ""
        assert result.severity == Severity.INFO


def test_ask_llm_groq_timeout():
    drain_all()
    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        side_effect=Exception("Request timed out"),
    ):
        result = ask_llm("Hello")
        assert "trouble connecting to my intelligence core" in result.text
        assert result.severity == Severity.ERROR


def test_ask_llm_groq_connection_error():
    drain_all()
    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        side_effect=Exception("Connection refused"),
    ):
        result = ask_llm("Hello")
        assert "trouble connecting to my intelligence core" in result.text
        assert result.severity == Severity.ERROR
