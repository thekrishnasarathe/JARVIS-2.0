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



class CompatLabel:
    def __init__(self, get_val_fn):
        self.get_val_fn = get_val_fn

    def text(self) -> str:
        return f"{float(self.get_val_fn())}%"



# ---------------------------------------------------------
# Main JARVIS 3D Application
# ---------------------------------------------------------

class TechHeaderWidget(QWidget):
    def __init__(self, text, color="#00E5FF", parent=None):
        super().__init__(parent)
        self.text = text
        self.color = QColor(color)
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(15)
        glow.setColor(self.color)
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)
        self.setFixedHeight(30)
        self.font = QFont("Orbitron", 10, QFont.Weight.Bold)
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(self.color)
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(self.width() - 20, 0)
        path.lineTo(self.width(), 20)
        path.lineTo(self.width(), self.height())
        path.lineTo(0, self.height())
        path.closeSubpath()
        
        painter.fillPath(path, QColor(self.color.red(), self.color.green(), self.color.blue(), 50))
        painter.setPen(QPen(self.color, 1))
        painter.drawPath(path)
        
        painter.setPen(self.color)
        painter.setFont(self.font)
        painter.drawText(QRectF(10, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text)
        painter.end()

class SubsystemBadge(QWidget):
    def __init__(self, icon_char, title, status, color="#E58B55", parent=None):
        super().__init__(parent)
        self.setFixedHeight(35)
        self.icon_char = icon_char
        self.title = title
        self.status = status
        self.color = QColor(color)
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(15)
        glow.setColor(self.color)
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        icon_rect = QRectF(0, 0, 35, 35)
        painter.setPen(QPen(self.color, 1))
        painter.drawRect(icon_rect)
        painter.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, self.icon_char)
        
        painter.setPen(QColor("#A8D8EA"))
        painter.setFont(QFont("Orbitron", 9))
        painter.drawText(QRectF(45, 0, 100, 35), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        
        path = QPainterPath()
        sw = 80
        sx = self.width() - sw
        path.moveTo(sx, 0)
        path.lineTo(self.width(), 0)
        path.lineTo(self.width(), 35)
        path.lineTo(sx + 10, 35)
        path.lineTo(sx, 25)
        path.closeSubpath()
        
        painter.fillPath(path, QColor(self.color.red(), self.color.green(), self.color.blue(), 40))
        painter.setPen(QPen(self.color, 1))
        painter.drawPath(path)
        
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Orbitron", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(sx, 0, sw, 35), Qt.AlignmentFlag.AlignCenter, self.status)
        painter.end()

class ChatBubbleWidget(QWidget):
    def __init__(self, sender, text, is_ai=True, parent=None):
        super().__init__(parent)
        self.sender_name = sender
        self.msg_text = text
        self.is_ai = is_ai
        self.color = QColor("#00E5FF") if is_ai else QColor("#D47A4A")
        # Estimate height based on text length
        lines = len(text) // 30 + 1
        self.setMinimumHeight(40 + lines * 15)
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(self.color)
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.moveTo(10, 0)
        path.lineTo(self.width(), 0)
        path.lineTo(self.width(), self.height())
        path.lineTo(0, self.height())
        path.lineTo(0, 10)
        path.closeSubpath()
        
        painter.fillPath(path, QColor(self.color.red(), self.color.green(), self.color.blue(), 20))
        painter.setPen(QPen(self.color, 1))
        painter.drawPath(path)
        
        painter.setFont(QFont("Orbitron", 9, QFont.Weight.Bold))
        painter.drawText(QRectF(15, 5, self.width()-20, 20), Qt.AlignmentFlag.AlignLeft, self.sender_name)
        
        painter.setPen(QColor("#E0E0E0"))
        painter.setFont(QFont("Courier New", 9))
        rect = QRectF(15, 25, self.width()-30, self.height()-30)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self.msg_text)
        painter.end()

class AdvancedCpuWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 160)
        self.cpu_val = 0
        self.rotation_angle = 0
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate)
        self.anim_timer.start(30)
        
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(25)
        glow.setColor(QColor("#00E5FF"))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def _animate(self):
        self.rotation_angle = (self.rotation_angle + 1) % 360
        self.update()

    def setValue(self, val):
        self.cpu_val = val
        self.update()

    def value(self):
        return self.cpu_val

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(10, 10, 140, 140)
        
        painter.setPen(QPen(QColor("#00E5FF"), 2))
        painter.drawArc(c, 0, 360 * 16)
        
        painter.save()
        painter.translate(c.center())
        painter.rotate(self.rotation_angle)
        painter.setPen(QPen(QColor("#00E5FF"), 6))
        c_centered = QRectF(-70, -70, 140, 140)
        for i in range(12):
            painter.drawArc(c_centered.adjusted(8,8,-8,-8), i * 30 * 16, 20 * 16)
        painter.restore()
            
        pen_bg = QPen(QColor("#1A2530"), 10)
        painter.setPen(pen_bg)
        painter.drawArc(c.adjusted(24,24,-24,-24), 0, 360 * 16)
        
        if self.cpu_val > 0:
            gradient = QConicalGradient(c.center(), -90)
            gradient.setColorAt(0, QColor("#00E5FF"))
            gradient.setColorAt(1, QColor("#D47A4A"))
            pen_fg = QPen(QBrush(gradient), 10)
            painter.setPen(pen_fg)
            painter.drawArc(c.adjusted(24,24,-24,-24), -90 * 16, int((self.cpu_val / 100.0) * 360 * 16))
            
        painter.setBrush(QColor("#00E5FF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(c.center(), 15, 15)
        painter.end()

class HUDLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 100)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.pulse = 0
        self.pulse_dir = 1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(50)
        
    def _animate(self):
        self.pulse += 5 * self.pulse_dir
        if self.pulse >= 100:
            self.pulse_dir = -1
        elif self.pulse <= 0:
            self.pulse_dir = 1
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.moveTo(20, 0)
        path.lineTo(self.width()-20, 0)
        path.lineTo(self.width(), 20)
        path.lineTo(self.width(), self.height())
        path.lineTo(0, self.height())
        path.lineTo(0, 20)
        path.closeSubpath()
        
        bg_alpha = 10 + int(self.pulse * 0.3)
        painter.fillPath(path, QColor(0, 229, 255, bg_alpha))
        painter.setPen(QPen(QColor(0, 229, 255, 155 + self.pulse), 2))
        painter.drawPath(path)
        
        painter.setPen(QColor("#00E5FF"))
        painter.setFont(QFont("Orbitron", 12, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 10, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "STARK ARC REACTOR")
        painter.setFont(QFont("Courier New", 10))
        painter.drawText(QRectF(0, 35, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "MARK LXXXV")
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(0, 55, self.width(), 40), Qt.AlignmentFlag.AlignCenter, "POWER OUTPUT: 100%\nSTABLE")
        painter.end()


class CircularCpuWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self.cpu_val = 0

    def setValue(self, val):
        self.cpu_val = val
        self.update()

    def value(self):
        return self.cpu_val

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(10, 10, 100, 100)

        # Background arc
        pen_bg = QPen(QColor("#1A2530"), 8)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, -45 * 16, 270 * 16)

        # Foreground arc
        if self.cpu_val > 0:
            gradient = QConicalGradient(rect.center(), -45)
            gradient.setColorAt(0, QColor("#D47A4A"))
            gradient.setColorAt(1, QColor("#00E5FF"))

            pen_fg = QPen(QBrush(gradient), 8)
            pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_fg)
            span_angle = int((self.cpu_val / 100.0) * 270 * 16)
            painter.drawArc(rect, -45 * 16, span_angle)

        # Outer ring
        pen_outer = QPen(QColor("#0D2030"), 2)
        painter.setPen(pen_outer)
        painter.drawEllipse(QRectF(2, 2, 116, 116))

        # Center Text
        painter.setPen(QColor("#00E5FF"))
        font = QFont("Orbitron", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.cpu_val}%")

        painter.end()


