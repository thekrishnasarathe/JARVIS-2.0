from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock

import pytest


# ─── Mock pyttsx3 before any import ──────────────────────────────────
class MockTTSVoice:
    def __init__(self, id, name):
        self.id = id
        self.name = name


mock_voice_1 = MockTTSVoice(id="david_id", name="David")
mock_voice_2 = MockTTSVoice(id="zira_id", name="Zira")


class MockTTSEngine:
    def __init__(self):
        self.properties = {
            "rate": 150,
            "voice": "david_id",
            "voices": [mock_voice_1, mock_voice_2],
        }

    def getProperty(self, name):
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def say(self, text):
        pass

    def runAndWait(self):
        pass


mock_pyttsx3 = MagicMock()
mock_pyttsx3.init.return_value = MockTTSEngine()
sys.modules["pyttsx3"] = mock_pyttsx3

# ─── Mock SpeechRecognition before any import ────────────────────────
mock_sr = MagicMock()
mock_recognizer = MagicMock()
mock_recognizer.recognize_google.return_value = "mocked speech input"
mock_sr.Recognizer.return_value = mock_recognizer
mock_microphone = MagicMock()
mock_sr.Microphone.return_value = mock_microphone
sys.modules["speech_recognition"] = mock_sr

# ─── Mock PyAudio before any import ──────────────────────────────────
mock_pyaudio = MagicMock()
mock_pa_instance = MagicMock()
mock_stream = MagicMock()
mock_stream.read.return_value = b"\x00" * 1024
mock_pa_instance.open.return_value = mock_stream
mock_pyaudio.PyAudio.return_value = mock_pa_instance
sys.modules["pyaudio"] = mock_pyaudio

# ─── Mock pvporcupine before any import ──────────────────────────────
mock_porcupine = MagicMock()
mock_porcupine_instance = MagicMock()
mock_porcupine_instance.sample_rate = 16000
mock_porcupine_instance.frame_length = 512
mock_porcupine_instance.process.side_effect = [0, -1, -1, -1]
mock_porcupine.create.return_value = mock_porcupine_instance
sys.modules["pvporcupine"] = mock_porcupine

# ─── Mock pyautogui before any import ────────────────────────────────
mock_pag = MagicMock()
mock_img = MagicMock()
mock_pag.screenshot.return_value = mock_img
mock_pag.size.return_value = (1920, 1080)
sys.modules["pyautogui"] = mock_pag

# ─── Mock cv2 (OpenCV) before any import ─────────────────────────────
mock_cv2 = MagicMock()
mock_cap = MagicMock()
mock_cap.isOpened.return_value = True
mock_frame = MagicMock()
mock_cap.read.return_value = (True, mock_frame)
mock_cv2.VideoCapture.return_value = mock_cap

mock_cascade = MagicMock()
mock_cascade.empty.return_value = False
mock_cascade.detectMultiScale.return_value = [[50, 50, 100, 100]]
mock_cv2.CascadeClassifier.return_value = mock_cascade
mock_cv2.data.haarcascades = "mock_haarcascades_dir/"
sys.modules["cv2"] = mock_cv2

# ─── Mock pywhatkit before any import ──────────────────────────────
mock_pywhatkit = MagicMock()
mock_pywhatkit.playonyt = MagicMock()
mock_pywhatkit.search = MagicMock()
sys.modules["pywhatkit"] = mock_pywhatkit

# ─── Mock pyvista and pyvistaqt before any import ────────────────────
mock_pyvista = MagicMock()
mock_pyvistaqt = MagicMock()

from PyQt6.QtWidgets import QWidget


class MockQtInteractor:
    def __init__(self, parent=None, *args, **kwargs):
        self.interactor = QWidget(parent)

    def set_background(self, *args, **kwargs):
        pass

    def enable_anti_aliasing(self, *args, **kwargs):
        pass

    def add_mesh(self, *args, **kwargs):
        return MagicMock()

    def close(self):
        pass


mock_pyvistaqt.QtInteractor = MockQtInteractor
sys.modules["pyvista"] = mock_pyvista
sys.modules["pyvistaqt"] = mock_pyvistaqt

# ─── Intercept sqlite3.connect for memory database isolation ──────────
temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.close(temp_db_fd)

original_connect = sqlite3.connect


def isolated_connect(*args, **kwargs):
    if len(args) > 0 and isinstance(args[0], str) and "jarvis_memory.db" in args[0]:
        return original_connect(temp_db_path, **kwargs)
    return original_connect(*args, **kwargs)


sqlite3.connect = isolated_connect


# ─── Clean up database after test session ────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_db():
    yield
    try:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
    except Exception:
        pass


# ─── Session fixtures that return the module-level mocks if tests need them ───
@pytest.fixture(scope="session")
def speech_recognition_mock():
    return mock_sr


@pytest.fixture(scope="session")
def pyaudio_mock():
    return mock_pyaudio


@pytest.fixture(scope="session")
def pvporcupine_mock():
    return mock_porcupine


@pytest.fixture(scope="session")
def pyautogui_mock():
    return mock_pag


@pytest.fixture(scope="session")
def cv2_mock():
    return mock_cv2
