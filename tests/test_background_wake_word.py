from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

from backend.background.wake_word import _wake_word_loop, start_wake_word_engine, stop_wake_word_engine
from shared.event_bus import drain_all
from shared.schemas import Severity


def test_wake_word_model_load_failure():
    drain_all()
    # Mock Model to raise Exception
    with patch("backend.background.wake_word.Model", side_effect=Exception("Model not found")):
        _wake_word_loop()

        # It should exit gracefully after failing to load model
        events = drain_all()
        # It logs error but doesn't push event on failure, so events are 0
        assert len(events) == 0


def test_wake_word_microphone_permission_error():
    drain_all()
    # Mock Model to succeed but pyaudio to crash
    with (
        patch("backend.background.wake_word.Model"),
        patch("pyaudio.PyAudio", side_effect=Exception("Microphone permission denied")),
    ):
        _wake_word_loop()

        events = drain_all()
        # Microphone error logs but doesn't push event
        assert len(events) == 0


def test_wake_word_detection_payloads():
    drain_all()

    # Mock Model instance
    mock_model_instance = MagicMock()
    # Return wake word detected
    mock_model_instance.predict.return_value = {"hey_jarvis": 0.9}

    # Mock pyaudio stream
    mock_stream = MagicMock()
    # returns dummy audio bytes
    mock_stream.read.return_value = b"\x00" * 1280

    mock_pa_instance = MagicMock()
    mock_pa_instance.open.return_value = mock_stream

    with (
        patch("backend.background.wake_word.Model", return_value=mock_model_instance),
        patch("pyaudio.PyAudio", return_value=mock_pa_instance),
        patch("backend.background.wake_word._stop_event") as mock_stop_event,
        patch("backend.background.wake_word._on_wake_word_detected") as mock_on_detected,
    ):
        # First check is not set, then second check is set to exit
        mock_stop_event.is_set.side_effect = [False, True]

        # Run loop
        _wake_word_loop()

        # Verify detection is called
        mock_on_detected.assert_called_once()

        # Check audio stream state transitions
        mock_stream.stop_stream.assert_called_once()
        
        events = drain_all()
        assert len(events) >= 1
        
        # Event 1: Online
        evt_start = [e for e in events if e.data and e.data.get("type") == "wake_word_ready"]
        assert len(evt_start) == 1
        assert "Wake word engine online." in evt_start[0].message


def test_start_wake_word_engine():
    # Verify starter returns thread
    with patch("backend.background.wake_word._wake_word_loop") as mock_loop:
        thread = start_wake_word_engine()
        assert isinstance(thread, threading.Thread)
        # Shutdown cleanly
        stop_wake_word_engine()
        thread.join(timeout=1.0)
