from __future__ import annotations

import pytest
import threading
import pyaudio
import pvporcupine
from unittest.mock import patch, MagicMock
from backend.background.wake_word import _wake_word_loop, start_wake_word_engine
from shared.event_bus import drain_all
from shared.schemas import Severity, CommandResult
from shared import config

def test_wake_word_missing_api_key():
    drain_all()
    # Mock config key to default/missing value
    with patch("shared.config.PORCUPINE_ACCESS_KEY", "YOUR_PORCUPINE_ACCESS_KEY"):
        stop_event = threading.Event()
        _wake_word_loop(stop_event)
        
        events = drain_all()
        assert len(events) == 1
        assert events[0].source == "wake_word"
        assert events[0].severity == Severity.ERROR
        assert "Missing API key" in events[0].message

def test_wake_word_microphone_permission_error():
    drain_all()
    # Mock pvporcupine to succeed but pyaudio to crash
    with patch("shared.config.PORCUPINE_ACCESS_KEY", "valid_access_key"), \
         patch("pvporcupine.create") as mock_porcupine_create, \
         patch("pyaudio.PyAudio", side_effect=Exception("Microphone permission denied")):
         
        stop_event = threading.Event()
        _wake_word_loop(stop_event)
        
        events = drain_all()
        assert len(events) == 1
        assert events[0].source == "wake_word"
        assert events[0].severity == Severity.ERROR
        assert "Microphone permission denied" in events[0].message

def test_wake_word_detection_and_routing_payloads():
    drain_all()
    
    stop_event = threading.Event()
    
    # Mock pvporcupine create and instance
    mock_porcupine_instance = MagicMock()
    mock_porcupine_instance.sample_rate = 16000
    mock_porcupine_instance.frame_length = 512
    # Return 0 (wake word detected) on first process call
    mock_porcupine_instance.process.return_value = 0
    
    # Mock pyaudio stream
    mock_stream = MagicMock()
    # returns dummy audio bytes
    mock_stream.read.return_value = b'\x00' * 1024
    
    mock_pa_instance = MagicMock()
    mock_pa_instance.open.return_value = mock_stream
    
    with patch("shared.config.PORCUPINE_ACCESS_KEY", "valid_access_key"), \
         patch("pvporcupine.create", return_value=mock_porcupine_instance), \
         patch("pyaudio.PyAudio", return_value=mock_pa_instance), \
         patch("backend.core.stt.take_command", return_value="run diagnostics") as mock_take_command, \
         patch("backend.core.router.process_command") as mock_process_command:
         
        # Mock process command to return success and set the stop event to exit loop
        def mock_process(query):
            stop_event.set()
            return CommandResult(text="Scan Complete", continue_loop=True)
        mock_process_command.side_effect = mock_process
        
        # Run loop
        _wake_word_loop(stop_event)
        
        # Verify STT and Router are invoked
        mock_take_command.assert_called_once()
        mock_process_command.assert_called_once_with("run diagnostics")
        
        # Check audio stream state transitions
        mock_stream.stop_stream.assert_called_once()
        # Verify events pushed to Event Bus
        events = drain_all()
        assert len(events) >= 3
        
        # Event 1: Listening started
        evt_start = [e for e in events if e.data and e.data.get("type") == "listening" and e.data.get("state") == "start"]
        assert len(evt_start) == 1
        assert "Listening for voice command" in evt_start[0].message
        
        # Event 2: Voice interaction processed (transcription and response details)
        evt_interaction = [e for e in events if e.data and e.data.get("type") == "voice_interaction"]
        assert len(evt_interaction) == 1
        assert evt_interaction[0].data["query"] == "run diagnostics"
        assert evt_interaction[0].data["response"] == "Scan Complete"
        assert "Voice query processed" in evt_interaction[0].message
        
        # Event 3: Listening stopped
        evt_stop = [e for e in events if e.data and e.data.get("type") == "listening" and e.data.get("state") == "stop"]
        assert len(evt_stop) == 1
        assert "Stopped listening" in evt_stop[0].message

def test_start_wake_word_engine():
    # Verify starter returns thread and event tuple
    with patch("backend.background.wake_word._wake_word_loop") as mock_loop:
        thread, stop_event = start_wake_word_engine()
        assert isinstance(thread, threading.Thread)
        assert isinstance(stop_event, threading.Event)
        # Shutdown cleanly
        stop_event.set()
        thread.join(timeout=1.0)
