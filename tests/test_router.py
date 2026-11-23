from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.core.router import process_command
from shared.schemas import Severity


def test_router_exit_command():
    result = process_command("goodbye")
    assert result.continue_loop is False
    assert "Goodbye" in result.text


def test_router_battery_command():
    with patch("psutil.sensors_battery") as mock_battery:
        mock_battery_instance = MagicMock()
        mock_battery_instance.percent = 85
        mock_battery_instance.power_plugged = True
        mock_battery.return_value = mock_battery_instance

        result = process_command("check battery")
        assert result.source == "system_utils"
        assert "85 percent" in result.text
        assert "plugged in" in result.text
        assert result.severity == Severity.INFO


def test_router_battery_command_low():
    with patch("psutil.sensors_battery") as mock_battery:
        mock_battery_instance = MagicMock()
        mock_battery_instance.percent = 15
        mock_battery_instance.power_plugged = False
        mock_battery.return_value = mock_battery_instance

        result = process_command("check battery")
        assert "15 percent" in result.text
        assert "not plugged in" in result.text
        # Low battery and not plugged in triggers warning based on config.BATTERY_LOW_THRESHOLD=20
        assert result.severity == Severity.WARNING


def test_router_battery_command_none():
    with patch("psutil.sensors_battery", return_value=None):
        result = process_command("check battery")
        assert "No battery detected" in result.text


def test_router_calculate_command():
    result = process_command("what is 5 plus 3")
    assert "8" in result.text

    result = process_command("7 times 6")
    assert "42" in result.text

    result = process_command("10 divide 0")
    assert "cannot divide by zero" in result.text


def test_router_joke_command():
    with patch("pyjokes.get_joke", return_value="Funny joke"):
        result = process_command("tell me a joke")
        assert "Funny joke" in result.text


def test_router_system_status_command():
    result = process_command("system status")
    assert "Running on" in result.text


def test_router_llm_fallback():
    # Since ask_llm goes to Groq API, we patch completions.create
    mock_choice = MagicMock()
    mock_choice.message.content = "This is LLM explaining quantum physics."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch(
        "backend.core.llm_fallback._client.chat.completions.create",
        return_value=mock_response,
    ):
        result = process_command("explain quantum physics")
        assert "quantum physics" in result.text or "LLM" in result.text


def test_router_wikipedia_command():
    with patch(
        "wikipedia.summary", return_value="Python is a programming language."
    ) as mock_summary:
        result = process_command("wikipedia Python")
        mock_summary.assert_called_once_with("python", sentences=2)
        assert "Python is a programming language." in result.text
        assert result.source == "web_services"


def test_router_play_youtube_command():
    with patch("pywhatkit.playonyt") as mock_play:
        result = process_command("play shape of you")
        mock_play.assert_called_once_with("shape of you")
        assert "Playing shape of you on YouTube" in result.text
        assert result.source == "system_utils"


def test_router_google_search_command():
    with patch("pywhatkit.search") as mock_search:
        result = process_command("google search python programming")
        mock_search.assert_called_once_with("python programming")
        assert "Searching Google for python programming" in result.text
        assert result.source == "system_utils"
