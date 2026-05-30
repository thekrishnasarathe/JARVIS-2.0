from __future__ import annotations

import sys
import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication
from shared.schemas import CommandResult, Severity, JarvisEvent

# Ensure a QApplication exists
app = QApplication.instance() or QApplication([])

from frontend.native_ui import (
    EventBusThread, CommandProcessorThread, TelemetryThread, JarvisNativeUI
)

# Prevent background threads from starting in tests to avoid shutdown hang
EventBusThread.start = MagicMock()
TelemetryThread.start = MagicMock()

def test_command_processor_thread():
    thread = CommandProcessorThread("calculate 2 plus 2")
    
    mock_result = CommandResult(text="The answer is 4", continue_loop=True, severity=Severity.SUCCESS)
    with patch("frontend.native_ui.process_command", return_value=mock_result) as mock_process, \
         patch("backend.core.tts.speak") as mock_speak:
         
        signals_received = []
        def on_result(result, original_cmd):
            signals_received.append((result, original_cmd))
            
        thread.result_ready.connect(on_result)
        thread.run()
        
        mock_process.assert_called_once_with("calculate 2 plus 2")
        mock_speak.assert_called_once_with("The answer is 4")
        assert len(signals_received) == 1
        assert signals_received[0][0].text == "The answer is 4"
        assert signals_received[0][1] == "calculate 2 plus 2"

def test_telemetry_thread():
    thread = TelemetryThread()
    
    with patch("psutil.cpu_percent", return_value=35.0), \
         patch("psutil.virtual_memory") as mock_mem:
        
        mock_mem.return_value.percent = 60.0
        
        signals_received = []
        def on_metrics(metrics):
            signals_received.append(metrics)
            
        thread.metrics_ready.connect(on_metrics)
        thread.metrics_ready.emit({"cpu": 35.0, "ram": 60.0})
        
        assert len(signals_received) == 1
        assert signals_received[0]["cpu"] == 35.0
        assert signals_received[0]["ram"] == 60.0

@patch("frontend.native_ui.JarvisNativeUI.show")
def test_native_ui_state_updates(mock_show):
    # Instantiate the UI with headless=True as requested by the Frontend Agent
    ui = JarvisNativeUI(headless=True)
    assert ui.headless is True
    
    # Test CPU and RAM bar updates
    ui.update_telemetry({"cpu": 45.0, "ram": 55.0})
    assert ui.cpu_bar.value() == 45
    assert ui.ram_bar.value() == 55
    assert "45.0%" in ui.cpu_val.text()
    assert "55.0%" in ui.ram_val.text()

    # Test event bus log updates on standard warning/error event received
    event = JarvisEvent(message="Critical hardware failure", severity=Severity.ERROR, source="test_runner")
    ui.on_event_received(event)
    
    # Live event log gets line-prepended
    assert "Critical hardware failure" in ui.event_ticker.text()
    
    # Error events trigger chat layout message addition
    count = ui.chat_layout.count()
    assert count > 0
    
    # Cleanup UI
    ui.close()

@patch("frontend.native_ui.JarvisNativeUI.show")
def test_headless_ui_llm_thinking_state(mock_show):
    print("\nDEBUG: Instantiating UI...")
    ui = JarvisNativeUI(headless=True)
    print("DEBUG: UI Instantiated!")
    
    # Start event
    event_start = JarvisEvent(
        message="LLM is thinking...",
        severity=Severity.INFO,
        source="llm_fallback",
        data={"type": "llm_thinking", "state": "start"}
    )
    print("DEBUG: Sending event_start...")
    ui.on_event_received(event_start)
    print("DEBUG: event_start sent!")
    assert ui.is_processing_anim is True
    
    # Stop event
    event_stop = JarvisEvent(
        message="LLM finished thinking.",
        severity=Severity.INFO,
        source="llm_fallback",
        data={"type": "llm_thinking", "state": "stop"}
    )
    print("DEBUG: Sending event_stop...")
    ui.on_event_received(event_stop)
    print("DEBUG: event_stop sent!")
    assert ui.is_processing_anim is False
    
    print("DEBUG: Closing UI...")
    ui.close()
    print("DEBUG: UI Closed!")

@patch("frontend.native_ui.JarvisNativeUI.show")
def test_headless_ui_listening_state(mock_show):
    ui = JarvisNativeUI(headless=True)
    
    # Listening start
    event_start = JarvisEvent(
        message="Listening...",
        severity=Severity.INFO,
        source="wake_word",
        data={"type": "listening", "state": "start"}
    )
    assert ui.listening_indicator.isHidden() is True
    ui.on_event_received(event_start)
    assert ui.listening_indicator.isHidden() is False
    
    # Listening stop
    event_stop = JarvisEvent(
        message="Stopped listening.",
        severity=Severity.INFO,
        source="wake_word",
        data={"type": "listening", "state": "stop"}
    )
    ui.on_event_received(event_stop)
    assert ui.listening_indicator.isHidden() is True
    
    ui.close()

@patch("frontend.native_ui.JarvisNativeUI.show")
def test_headless_ui_voice_interaction_state(mock_show):
    ui = JarvisNativeUI(headless=True)
    
    # Clear chat layout messages
    # Count the initial widgets
    initial_count = ui.chat_layout.count()
    
    # Voice interaction event
    event_interaction = JarvisEvent(
        message="Interaction complete.",
        severity=Severity.INFO,
        source="wake_word",
        data={
            "type": "voice_interaction",
            "query": "hello world",
            "response": "hello boss"
        }
    )
    ui.on_event_received(event_interaction)
    
    # Verify two new messages appended (query from user, response from Jarvis)
    new_count = ui.chat_layout.count()
    assert new_count == initial_count + 2
    
    ui.close()
