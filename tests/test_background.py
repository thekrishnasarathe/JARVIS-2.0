from __future__ import annotations

import pytest
import threading
from unittest.mock import patch, MagicMock
from backend.background.battery_monitor import _battery_check_loop
from backend.background.face_monitor import _face_check_loop
from shared.event_bus import drain_all
from shared.schemas import Severity
from shared import config

def test_battery_monitor_loop():
    # Empty the event queue first
    drain_all()
    
    # Mock psutil
    with patch("psutil.sensors_battery") as mock_battery, \
         patch("shared.config.BATTERY_LOW_THRESHOLD", 20):
         
        mock_batt = MagicMock()
        mock_batt.percent = 15
        mock_batt.power_plugged = False
        mock_battery.return_value = mock_batt
        
        # We want the loop to execute exactly once, so we set the stop event
        stop_event = threading.Event()
        
        # Patch the wait method on stop_event so it exits immediately
        original_wait = stop_event.wait
        def mock_wait(timeout=None):
            stop_event.set() # Set stop event during the first iteration wait
            return True
        stop_event.wait = mock_wait
        
        _battery_check_loop(stop_event)
        
        # Verify event was pushed
        events = drain_all()
        assert len(events) > 0
        low_batt_events = [e for e in events if e.source == "battery_monitor" and e.severity == Severity.WARNING]
        assert len(low_batt_events) == 1
        assert "Battery critically low" in low_batt_events[0].message

def test_face_monitor_loop_lock():
    # Empty the event queue first
    drain_all()
    
    # Create a dynamic mock time to avoid StopIteration during logging calls
    call_count = 0
    def mock_time():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return 1000.0
        return 1000.5

    from backend.modules.security import FaceStatus
    with patch("backend.background.face_monitor.verify_authorized_user", return_value=FaceStatus.NO_FACE), \
         patch("backend.background.face_monitor.lock_workstation") as mock_lock, \
         patch("shared.config.SECURITY_FACE_TIMEOUT", 0.1), \
         patch("shared.config.SECURITY_CHECK_INTERVAL", 0.05), \
         patch("time.time", side_effect=mock_time):
         
        stop_event = threading.Event()
        
        # Mock wait to set stop_event after the first check
        def mock_wait(timeout=None):
            stop_event.set()
            return True
        stop_event.wait = mock_wait
        
        # Set face timeout to 0 so it locks immediately
        _face_check_loop(stop_event)
        
        # Verify lock was called and event pushed
        mock_lock.assert_called_once()
        events = drain_all()
        assert len(events) > 0
        face_events = [e for e in events if e.source == "face_monitor" and e.severity == Severity.WARNING]
        assert len(face_events) == 1
        assert "Locking workstation" in face_events[0].message
