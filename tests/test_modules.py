from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

# ─── System Utils Tests ──────────────────────────────────────────────
from backend.modules.system_utils import take_note, take_screenshot, tell_datetime
from shared.schemas import Severity


def test_tell_datetime():
    # Test date and time
    result = tell_datetime("what is the date and time")
    assert "Today is" in result.text
    assert "and the time is" in result.text

    # Test date only
    result = tell_datetime("what is the date")
    assert "Today's date is" in result.text
    assert "time" not in result.text.lower()

    # Test time only
    result = tell_datetime("what is the time")
    assert "The time is" in result.text
    assert "date" not in result.text.lower()


def test_take_screenshot():
    # pyautogui is mocked globally in conftest.py
    with patch("shared.config.DESKTOP_PATH", tempfile.gettempdir()):
        result = take_screenshot("take a screenshot")
        assert result.severity == Severity.SUCCESS
        assert "screenshot_" in result.text


def test_take_note_via_command():
    temp_dir = tempfile.mkdtemp()
    notes_file = os.path.join(temp_dir, "notes.txt")
    with patch("shared.config.NOTES_FILE", notes_file):
        result = take_note("note that clean tests are vital")
        assert result.severity == Severity.SUCCESS
        assert "clean tests are vital" in open(notes_file, "r", encoding="utf-8").read()


def test_take_note_fallback():
    # If no note content, it uses take_command which is mocked to return "mocked speech input"
    temp_dir = tempfile.mkdtemp()
    notes_file = os.path.join(temp_dir, "notes.txt")
    with (
        patch("shared.config.NOTES_FILE", notes_file),
        patch("backend.core.tts.speak") as mock_speak,
        patch(
            "backend.modules.system_utils.take_command",
            return_value="mocked speech input",
        ),
    ):
        result = take_note("write a note")
        assert result.severity == Severity.SUCCESS
        assert "mocked speech input" in open(notes_file, "r", encoding="utf-8").read()


# ─── Memory Tests ────────────────────────────────────────────────────
from backend.modules.memory import get_engine, recall_command, remember_command


def test_memory_engine_isolation():
    engine = get_engine()
    engine.remember("JARVIS stands for Just A Rather Very Intelligent System")

    results = engine.recall("What does JARVIS stand for?")
    assert len(results) > 0
    assert "JARVIS stands for" in results[0]["content"]

    stats = engine.get_stats()
    assert stats["total_memories"] >= 1

    # Check commands
    rem_res = remember_command("remember that tests are passing")
    assert rem_res.severity == Severity.SUCCESS

    recall_res = recall_command("recall tests")
    assert "tests are passing" in recall_res.text


# ─── Diagnostics Tests ───────────────────────────────────────────────
from backend.modules.diagnostics import network_check, system_scan, top_processes


def test_system_scan():
    with (
        patch("psutil.cpu_percent", return_value=15.0),
        patch("psutil.virtual_memory") as mock_mem,
        patch("psutil.disk_usage") as mock_disk,
        patch("psutil.net_io_counters") as mock_net,
    ):

        mock_mem.return_value.percent = 40.0
        mock_mem.return_value.used = 4 * 1024 * 1024 * 1024
        mock_mem.return_value.total = 10 * 1024 * 1024 * 1024

        mock_disk.return_value.percent = 50.0
        mock_disk.return_value.used = 50 * 1024 * 1024 * 1024
        mock_disk.return_value.total = 100 * 1024 * 1024 * 1024

        mock_net.return_value.bytes_sent = 1024 * 1024
        mock_net.return_value.bytes_recv = 2 * 1024 * 1024

        result = system_scan("run diagnostics")
        assert "Health: 100/100" in result.text
        assert "CPU: 15" in result.text
        assert "RAM: 40" in result.text
        assert "System Drive: 50" in result.text


def test_top_processes():
    # psutil is mocked to return process iterator
    with patch("psutil.process_iter") as mock_iter:
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 1234,
            "name": "python",
            "cpu_percent": 12.5,
            "memory_percent": 2.0,
        }
        mock_proc.cpu_percent.return_value = 12.5
        mock_iter.return_value = [mock_proc]

        result = top_processes("top processes")
        assert "python" in result.text
        assert "1234" in result.text


def test_network_check():
    with (
        patch("socket.gethostbyname", return_value="127.0.0.1"),
        patch("psutil.net_if_addrs") as mock_addrs,
        patch("psutil.net_if_stats") as mock_stats,
    ):

        # Mock address & stats
        mock_addrs.return_value = {
            "Ethernet": [MagicMock(family=2, address="192.168.1.10")]
        }  # 2 is socket.AF_INET
        mock_nic_stat = MagicMock()
        mock_nic_stat.isup = True
        mock_stats.return_value = {"Ethernet": mock_nic_stat}

        result = network_check("network check")
        assert "ONLINE" in result.text
        assert "Ethernet" in result.text


# ─── File Intel Tests ────────────────────────────────────────────────
from backend.modules.file_intel import find_files, largest_files


def test_find_files():
    with patch("os.walk") as mock_walk, patch("os.path.getsize", return_value=1234):
        # walk returns: root, dirs, files
        mock_walk.return_value = [("/home/user/Documents", [], ["report_test.txt"])]

        result = find_files("find files named report_test")
        assert "report_test.txt" in result.text


def test_largest_files():
    with (
        patch(
            "backend.modules.file_intel._get_common_dirs", return_value=["/dummy/dir"]
        ),
        patch("os.walk") as mock_walk,
        patch("os.path.getsize", return_value=5000000),
    ):

        mock_walk.return_value = [("/dummy/dir", [], ["large_file.zip"])]

        result = largest_files("largest files")
        assert "large_file.zip" in result.text


# ─── Automation Tests ────────────────────────────────────────────────
from backend.modules.automation import cancel_reminder, list_reminders, set_reminder


def test_reminders_lifecycle():
    # Clear reminders first
    import backend.modules.automation as automation

    with automation._reminder_lock:
        automation._active_reminders.clear()

    # Set reminder
    res = set_reminder("remind me in 2 seconds to drink water")
    assert res.severity == Severity.SUCCESS

    # Check that it got registered in active reminders
    assert len(automation._active_reminders) == 1
    rem_id = list(automation._active_reminders.keys())[0]
    assert "REM-" in rem_id

    # List reminders
    res_list = list_reminders("list reminders")
    assert "drink water" in res_list.text

    # Cancel reminder using the actual ID
    res_cancel = cancel_reminder(f"cancel reminder {rem_id}")
    assert "cancelled" in res_cancel.text


# ─── Security Tests ──────────────────────────────────────────────────
from backend.modules.security import check_face_present, lock_workstation


def test_security_face_present():
    # OpenCV is globally mocked to detect face
    assert check_face_present() is True


def test_lock_workstation():
    with patch("os.name", "nt"), patch("os.system") as mock_sys:
        lock_workstation()
        mock_sys.assert_called_once_with("rundll32.exe user32.dll,LockWorkStation")
