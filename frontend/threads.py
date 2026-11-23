import asyncio
import builtins
import logging
import os
import sys
import threading
import time
import types

# ─── VTK DLL Policy Workaround ──────────────────────────────────────
# Windows Application Control policies block certain VTK DLLs.
# Strategy:
#   1. Hook builtins.__import__ to catch DLL load failures for any
#      vtkmodules.* import and return a harmless stub automatically.
#   2. Pre-stub pyvista.plotting.charts (which triggers vtkChartsCore)
#      to prevent cascade failures in PyVista's plotting init.
# The hook is removed after pyvista/pyvistaqt are fully loaded.

class _VTKStubModule(types.ModuleType):
    """Fake VTK module — returns a dummy class for any attribute."""
    class _Dummy:
        def __init__(self, *a, **kw): pass
        def __init_subclass__(cls, **kw): pass
    def __getattr__(self, name):
        return self._Dummy

# Pre-stub the entire pyvista.plotting.charts module so PyVista
# never tries to load vtkChartsCore.  The stub returns a smart class
# for ANY attribute (Charts, Chart2D, ChartMPL, Axis, etc.).

class _ChartsMeta(type):
    """Metaclass: returns a dummy function for any missing class attribute."""
    def __getattr__(cls, name):
        def _dummy(*a, **kw): pass
        _dummy.__name__ = name
        _dummy.__qualname__ = f"{cls.__name__}.{name}"
        return _dummy

class _ChartsBase(metaclass=_ChartsMeta):
    def __init__(self, *a, **kw): pass

class _ChartsStubModule(types.ModuleType):
    """Returns _ChartsBase for any name imported from this module."""
    def __getattr__(self, name):
        # Return a new class named after the requested attribute
        return _ChartsMeta(name, (_ChartsBase,), {})

sys.modules["pyvista.plotting.charts"] = _ChartsStubModule("pyvista.plotting.charts")

_real_import = builtins.__import__

def _vtk_safe_import(name, *args, **kwargs):
    try:
        return _real_import(name, *args, **kwargs)
    except ImportError as e:
        err_msg = str(e)
        if "vtk" in name.lower() and ("DLL" in err_msg or "Application Control" in err_msg):
            mod = _VTKStubModule(name)
            sys.modules[name] = mod
            return mod
        raise

builtins.__import__ = _vtk_safe_import

import numpy as np
import psutil
import pyvista as pv

# ─── pyvista 0.48 / pyvistaqt 0.11 compatibility shim ───────────────
# pyvistaqt 0.11 does `from pyvista import global_theme` but pyvista 0.48
# renamed it to `global_config`.  Alias it so the import succeeds.
if not hasattr(pv, "global_theme"):
    pv.global_theme = pv.global_config
from PyQt6.QtCore import QPoint, QRectF, Qt, QThread, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QPolygonF,
    QPainterPath,
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontDatabase,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

# Restore original import now that pyvista/pyvistaqt are fully loaded
builtins.__import__ = _real_import

from backend.core.router import process_command
from backend.modules import memory as mem_module
from backend.modules.spatial_memory.graph_builder import COLOR_MAP, build_graph_from_memory
from backend.modules.spatial_memory.graph_persistence import (
    load_positions,
    migrate_memory_table,
    save_positions,
)
from backend.modules.spatial_memory.graph_physics import GraphNode, PhysicsEngine
from shared.event_bus import poll_event, push_event
from shared.graph_schemas import NodeEvent
from shared.schemas import CommandResult, JarvisEvent, Severity

logger = logging.getLogger(__name__)



# ---------------------------------------------------------
# Background Threads
# ---------------------------------------------------------
class EventBusThread(QThread):
    event_received = pyqtSignal(object)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def poll_loop():
            while True:
                event = await poll_event(timeout=0.5)
                if event is not None:
                    self.event_received.emit(event)
                await asyncio.sleep(0.1)

        loop.run_until_complete(poll_loop())


class VoiceInputThread(QThread):
    result_ready = pyqtSignal(str)

    def run(self):
        try:
            from backend.core.stt import take_command
            push_event(JarvisEvent(
                message="Microphone ON. Listening...",
                severity=Severity.INFO,
                source="stt",
                data={"type": "listening", "state": "start"}
            ))
            
            text = take_command(timeout=10)
            
            push_event(JarvisEvent(
                message="Microphone OFF.",
                severity=Severity.INFO,
                source="stt",
                data={"type": "listening", "state": "stop"}
            ))
            
            self.result_ready.emit(text)
        except Exception as e:
            logger.error(f"Voice thread error: {e}")
            push_event(JarvisEvent(
                message="Microphone OFF due to error.",
                severity=Severity.ERROR,
                source="stt",
                data={"type": "listening", "state": "stop"}
            ))
            self.result_ready.emit("None")


class CommandProcessorThread(QThread):
    result_ready = pyqtSignal(object, str)

    def __init__(self, command_text: str):
        super().__init__()
        self.command_text = command_text

    def run(self):
        try:
            import frontend.native_ui
            result = frontend.native_ui.process_command(self.command_text)
            self.result_ready.emit(result, self.command_text)
            if result.text:
                try:
                    from backend.core.tts import speak

                    speak(result.text)
                except Exception:
                    pass
        except Exception as e:
            err_result = CommandResult(
                text=f"Command failed: {str(e)}",
                continue_loop=True,
                severity=Severity.ERROR,
            )
            self.result_ready.emit(err_result, self.command_text)


class TelemetryThread(QThread):
    metrics_ready = pyqtSignal(dict)

    def run(self):
        while True:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.metrics_ready.emit({"cpu": cpu, "ram": ram})
            time.sleep(1)


