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



from frontend.widgets import CompatLabel, TechHeaderWidget, SubsystemBadge, ChatBubbleWidget, AdvancedCpuWidget, HUDLabel, CircularCpuWidget
from frontend.memory_theater import MemoryTheater
from frontend.threads import EventBusThread, CommandProcessorThread, TelemetryThread, VoiceInputThread

class JarvisNativeUI(QMainWindow):
    def __init__(self, headless: bool = False):
        super().__init__()
        self.headless = headless
        self.setWindowTitle("JARVIS 2.0 - Core")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.resize(1500, 850)

        # For custom window dragging
        self._drag_pos = QPoint()

        # Apply Master QSS
        app = QApplication.instance()
        if app:
            QFontDatabase.addApplicationFont(
                "frontend/assets/fonts/Orbitron-Regular.ttf"
            )
            QFontDatabase.addApplicationFont("frontend/assets/fonts/Orbitron-Bold.ttf")

            master_qss = """
                QMainWindow, QWidget#MainWidget {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118);
                }
                QScrollArea {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118);
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118);
                }
                QLabel {
                    color: #2A4A5A;
                    font-family: 'Courier New';
                }
                QToolTip {
                    background-color: #121824;
                    border: 1px solid #00E5FF;
                    color: #00E5FF;
                }
            """
            app.setStyleSheet(master_qss)

        # Main Central Widget
        self.central_widget = QWidget()
        self.central_widget.setObjectName("MainWidget")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.init_title_bar()

        # Content Layout
        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 15, 15, 15)
        self.content_layout.setSpacing(15)

        self.init_telemetry_sidebar()

        if not self.headless:
            self._theater_mode = (
                os.getenv("JARVIS_THEATER_MODE", "false").lower() == "true"
            )
            self._memory_theater = None
            self.init_3d_core()

        self.init_dashboard()

        if not self.headless:
            self.main_layout.addWidget(self.content_widget, stretch=1)
        else:
            self.main_layout.addWidget(self.content_widget)

        # Start Threads
        self.event_thread = EventBusThread()
        self.event_thread.event_received.connect(self.on_event_received)
        self.event_thread.start()

        self.telemetry_thread = TelemetryThread()
        self.telemetry_thread.metrics_ready.connect(self.update_telemetry)
        self.telemetry_thread.start()

        self.active_command_thread = None
        self.is_lockdown = False
        self._theater_mode = os.getenv("JARVIS_THEATER_MODE", "false").lower() == "true"
        self._memory_theater: MemoryTheater | None = None

    # --- Title Bar & Drag Logic ---
    def init_title_bar(self):
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118); border-bottom: none;")

        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(15, 0, 15, 0)

        title_lbl = QLabel("STARK TECH | SYSTEM UI | 4K HDR")
        title_lbl.setStyleSheet("color: #A8D8EA; font-weight: bold; font-family: 'Orbitron'; font-size: 10px; letter-spacing: 2px; border: none;")
        layout.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # For compatibility
        self.listening_indicator = QLabel()
        self.clock_lbl = QLabel()
        self.toggle_btn = QPushButton()
        self.main_layout.addWidget(self.title_bar)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.pos().y() < self.title_bar.height()
        ):
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()

    # --- Telemetry Sidebar ---
    def init_telemetry_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(350)
        self.sidebar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118);
                border-right: 1px solid #00E5FF;
                border-radius: 0px;
            }
        """)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(TechHeaderWidget("SYSTEM STATUS", "#00E5FF"))
        layout.addWidget(TechHeaderWidget("REACTOR CORE 01", "#D47A4A"))

        # Core Widget
        self.cpu_widget = AdvancedCpuWidget()
        self.cpu_bar = self.cpu_widget
        self.cpu_val = CompatLabel(self.cpu_widget.value)
        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(self.cpu_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(cpu_layout)

        # Status Grid
        grid_frame = QFrame()
        grid_layout = QHBoxLayout(grid_frame)
        grid_layout.setContentsMargins(0,0,0,0)
        
        left_grid = QVBoxLayout()
        l1 = QLabel("STATUS: ONLINE")
        l1.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 10px;")
        l2 = QLabel("POWER: 98.7 GW")
        l2.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 10px;")
        l3 = QLabel("TEMP: 14.3 MK")
        l3.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 10px;")
        left_grid.addWidget(l1)
        left_grid.addWidget(l2)
        left_grid.addWidget(l3)
        grid_layout.addLayout(left_grid)
        
        right_grid = QVBoxLayout()
        r1 = QLabel("INTEGRITY: 99.5%")
        r1.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 10px;")
        r2 = QLabel("SHIELD: 100%")
        r2.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 10px;")
        r3 = QLabel("TEMP: OK")
        r3.setStyleSheet("color: #00E5FF; font-family: 'Orbitron'; font-size: 10px;")
        right_grid.addWidget(r1)
        right_grid.addWidget(r2)
        right_grid.addWidget(r3)
        grid_layout.addLayout(right_grid)
        
        layout.addWidget(grid_frame)

        # Subsytems
        layout.addWidget(TechHeaderWidget("SUBSYSTEMS", "#D47A4A"))
        layout.addWidget(SubsystemBadge("A", "REACTION:", "ACTIVE"))
        layout.addWidget(SubsystemBadge("O", "COOLING:", "STABLE"))
        layout.addWidget(SubsystemBadge("U", "CONDUITS:", "NOMINAL"))

        layout.addStretch()
        self.content_layout.addWidget(self.sidebar)

        self.ram_bar = QProgressBar()  # Dummy for compatibility
        self.ram_val = QLabel()
        self.cpu_val = QLabel()
        self.event_ticker = QLabel()

    def update_telemetry(self, metrics: dict):
        cpu = metrics["cpu"]
        ram = metrics["ram"]
        self.cpu_widget.setValue(int(cpu))
        self.cpu_val.setText(f"{int(cpu)}%")
        self.ram_bar.setValue(int(ram))
        self.ram_val.setText(f"{int(ram)}% ALLOCATED")

    # --- 3D VTK Core ---
    def init_3d_core(self):
        self.left_frame = QFrame()
        self.left_frame.setStyleSheet("border: 1px solid #0D2030; border-radius: 0px;")
        self.left_layout = QVBoxLayout(self.left_frame)
        self.left_layout.setContentsMargins(2, 2, 2, 2)

        self.plotter = QtInteractor(self.left_frame)
        self.plotter.set_background(color=(0, 0, 0), top=(0, 0, 0))
        self.plotter.renderer.SetBackground(0, 0, 0)
        self.plotter.renderer.GradientBackgroundOff()
        self.plotter.enable_anti_aliasing()
        self.left_layout.addWidget(self.plotter.interactor)

        # Camera
        self.plotter.camera_position = [(0, 0, 20), (0, 0, 0), (0, 1, 0)]
        self.arc_actors = []

        # Base Layer: Static Image Texture
        self.texture_path = r"C:\Users\krish\Downloads\Projects\JARVIS 2.0\frontend\assets\arc_reactor.jpg"
        
        if not os.path.exists(self.texture_path):
            logger.error(f"[ARC REACTOR] Image not found at {self.texture_path}")
        else:
            try:
                texture = pv.Texture(self.texture_path)
                texture.interpolate = True
                texture.mipmap = False
                texture.repeat = False

                img = texture.to_image()
                dims = img.GetDimensions()
                aspect = dims[0] / dims[1] if dims[1] != 0 else 1.0

                plane = pv.Plane(
                    center=(0, 0, 0),
                    direction=(0, 0, 1),
                    i_size=12.0 * aspect,
                    j_size=12.0,
                    i_resolution=200,
                    j_resolution=200
                )

                self.image_actor = self.plotter.add_mesh(
                    plane,
                    texture=texture,
                    lighting=False,
                    smooth_shading=False,
                )
                self.image_actor.GetProperty().SetAmbient(1.0)
                self.image_actor.GetProperty().SetDiffuse(0.0)
                self.image_actor.GetProperty().SetSpecular(0.0)

                self.arc_actors.append(self.image_actor)
                
                self.plotter.camera_position = [(0, 0, 18), (0, 0, 0), (0, 1, 0)]
                self.plotter.enable_parallel_projection()
            except Exception as e:
                print(f"[THEATER] Failed to load image texture: {e}")

        self.plotter.enable_2d_style()
        
        # Disable default VTK camera controls (pan/rotate) but keep the interactor 
        # enabled so PyVista's ray picking still functions perfectly!
        from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser
        style = vtkInteractorStyleUser()
        self.plotter.interactor.SetInteractorStyle(style)

        self.hud_overlay = HUDLabel(self.left_frame)
        self.content_layout.addWidget(self.left_frame, stretch=5)

        # Use a direct VTK observer on LeftButtonPressEvent instead of
        # enable_element_picking (which requires hitting a mesh cell and
        # silently fails with vtkInteractorStyleUser).
        self.plotter.interactor.AddObserver(
            'LeftButtonPressEvent',
            lambda obj, evt: self._on_viewport_click()
        )

        if getattr(self, "plotter", None) is None:
            return

        try:
            self._memory_theater = MemoryTheater(self.plotter)
            if getattr(self, "_theater_mode", False):
                self._memory_theater.activate()
        except Exception as e:
            print(f"[THEATER] Failed to initialize MemoryTheater: {e}")
            self._memory_theater = None

        self.start_time = time.time()
        self.is_processing_anim = False
        self.is_lockdown = False
        self._reactor_rotation = 0.0
        self.is_listening = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'hud_overlay') and hasattr(self, 'left_frame'):
            self.hud_overlay.move(self.left_frame.width() // 2 - 100, self.left_frame.height() - 50)

    def _on_viewport_click(self):
        """Fires on ANY click in the 3D viewport."""
        if not getattr(self, "_theater_mode", False):
            self.toggle_mic()

    def toggle_mic(self):
        if getattr(self, 'is_listening', False):
            if hasattr(self, 'voice_thread') and self.voice_thread.isRunning():
                self.voice_thread.terminate()
                self.voice_thread.wait()
            self.is_listening = False
            push_event(JarvisEvent(
                message="Microphone OFF (Cancelled).",
                severity=Severity.INFO,
                source="ui",
                data={"type": "listening", "state": "stop"}
            ))
            return
            
        self.is_listening = True
        self.voice_thread = VoiceInputThread()
        self.voice_thread.result_ready.connect(self.on_voice_result)
        self.voice_thread.start()
        
    def on_voice_result(self, text: str):
        self.is_listening = False
        if text and text != "None":
            # Simulate typing it and submitting it
            self.cmd_input.setText(text)
            self.submit_command()

    def _toggle_theater_mode(self):
        if self._memory_theater is None:
            return
            
        from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser, vtkInteractorStyleTrackballCamera
            
        if self._theater_mode:
            self._memory_theater.deactivate()
            if hasattr(self, "arc_actors"):
                for act in self.arc_actors:
                    self.plotter.add_actor(act)
            self._theater_mode = False
            self.toggle_btn.setText("◈ ARC VIEW")
            
            # Lock camera for arc view
            style = vtkInteractorStyleUser()
            self.plotter.interactor.SetInteractorStyle(style)
            
            self.plotter.set_background(color=(0, 0, 0), top=(0, 0, 0))
            self.plotter.renderer.SetBackground(0, 0, 0)
            self.plotter.renderer.GradientBackgroundOff()
            self.plotter.camera_position = [(0, 0, 20), (0, 0, 0), (0, 1, 0)]
        else:
            if hasattr(self, "arc_actors"):
                for act in self.arc_actors:
                    self.plotter.remove_actor(act)
            self._memory_theater.activate()
            self._theater_mode = True
            
            # Restore default Trackball camera for theater mode
            style = vtkInteractorStyleTrackballCamera()
            self.plotter.interactor.SetInteractorStyle(style)
            
            self.toggle_btn.setText("◈ REACTOR VIEW")

    def animate_core(self):
        if getattr(self, "_theater_mode", False):
            if not self.headless:
                self.plotter.interactor.Render()
            return

        if not self.headless:
            self.plotter.interactor.Render()

    # --- Holographic Chat Dashboard ---
    def init_dashboard(self):
        self.right_frame = QFrame()
        self.right_frame.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118); border-left: 1px solid #00E5FF;")
        self.right_frame.setMinimumWidth(350)
        self.right_layout = QVBoxLayout(self.right_frame)
        self.right_layout.setContentsMargins(20, 20, 20, 20)
        self.right_layout.setSpacing(15)
        
        self.right_layout.addWidget(TechHeaderWidget("OPERATOR TERMINAL", "#00E5FF"))
        self.right_layout.addWidget(TechHeaderWidget("OPERATOR LOG", "#D47A4A"))

        # Chat Feed
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118); }
            QScrollBar:vertical { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118); width: 4px; }
            QScrollBar::handle:vertical { background: #00E5FF; min-height: 20px; }
        """)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118);")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area.setWidget(self.chat_container)
        self.right_layout.addWidget(self.scroll_area, stretch=1)

        # Futuristic Input Deck
        self.input_deck = QFrame()
        self.input_deck.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #020305, stop:1 #0A1118);
                border: 1px solid #00E5FF;
                border-radius: 5px;
            }
        """)
        deck_layout = QHBoxLayout(self.input_deck)
        deck_layout.setContentsMargins(10, 5, 10, 5)

        sys_lbl = QLabel("> OPERATOR COMMAND:")
        sys_lbl.setStyleSheet("color: #FFFFFF; font-weight: bold; font-family: 'Orbitron'; font-size: 10px; border: none;")
        deck_layout.addWidget(sys_lbl)

        self.cmd_input = QLineEdit()
        self.cmd_input.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                color: #00E5FF;
                border: none;
                font-size: 11px;
                font-family: 'Courier New';
            }
        """)
        self.cmd_input.returnPressed.connect(self.submit_command)
        deck_layout.addWidget(self.cmd_input, stretch=1)

        self.submit_btn = QPushButton("TX")
        self.submit_btn.setFixedWidth(40)
        self.submit_btn.setStyleSheet("background: transparent; color: #00E5FF; border: none;")
        self.submit_btn.clicked.connect(self.submit_command)
        deck_layout.addWidget(self.submit_btn)

        self.right_layout.addWidget(self.input_deck)
        self.content_layout.addWidget(self.right_frame, stretch=3)

    def append_chat_message(self, sender: str, text: str, is_user: bool = False):
        if is_user:
            bubble = ChatBubbleWidget("T. STARK", text, is_ai=False)
        else:
            bubble = ChatBubbleWidget("J.A.R.V.I.S.", text, is_ai=True)
            
        self.chat_layout.addWidget(bubble)
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum()))

    def append_tool_widget(self, tool_name: str, args: dict):
        widget_frame = QFrame()
        widget_layout = QVBoxLayout(widget_frame)
        widget_layout.setContentsMargins(15, 12, 15, 12)

        # Tool Widget Styling (Glowing Amber/Yellow)
        widget_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 180, 255, 0.1);
                border: 1px solid rgba(0, 180, 255, 0.4);
                border-left: 4px solid #00B4FF;
                border-radius: 8px;
            }
        """)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("⚙️ TOOL EXECUTING")
        icon_lbl.setStyleSheet(
            "color: #00B4FF; font-weight: bold; font-size: 11px; border: none; font-family: Courier;"
        )

        name_lbl = QLabel(f"[{tool_name.upper()}]")
        name_lbl.setStyleSheet(
            "color: #A8D8EA; font-weight: bold; font-size: 11px; border: none; font-family: Courier;"
        )

        header_layout.addWidget(icon_lbl)
        header_layout.addStretch()
        header_layout.addWidget(name_lbl)

        args_text = (
            "\\n".join(f"{k}: {v}" for k, v in args.items())
            if args
            else "No arguments."
        )
        args_lbl = QLabel(args_text)
        args_lbl.setWordWrap(True)
        args_lbl.setStyleSheet(
            "color: #A8D8EA; font-size: 12px; border: none; margin-top: 5px; font-family: Courier;"
        )

        widget_layout.addLayout(header_layout)
        widget_layout.addWidget(args_lbl)

        self.chat_layout.addWidget(widget_frame)

        QTimer.singleShot(
            50,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def append_subagent_widget(self, role: str, status: str, result: str = None):
        widget_frame = QFrame()
        widget_layout = QVBoxLayout(widget_frame)
        widget_layout.setContentsMargins(15, 12, 15, 12)

        # Subagent Styling (Glowing Emerald/Green)
        widget_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(16, 185, 129, 0.1);
                border: 1px solid rgba(16, 185, 129, 0.4);
                border-left: 4px solid #10b981;
                border-radius: 8px;
            }
        """)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        if status == "WORKING":
            icon = "🔄 SUBAGENT SPAWNED"
            icon_color = "#34d399"
        else:
            icon = "✅ SUBAGENT COMPLETED"
            icon_color = "#10b981"

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"color: {icon_color}; font-weight: bold; font-size: 11px; border: none; font-family: Courier;"
        )

        name_lbl = QLabel(f"[{role.upper()}]")
        name_lbl.setStyleSheet(
            "color: #6ee7b7; font-weight: bold; font-size: 11px; border: none; font-family: Courier;"
        )

        header_layout.addWidget(icon_lbl)
        header_layout.addStretch()
        header_layout.addWidget(name_lbl)

        widget_layout.addLayout(header_layout)

        if result:
            result_lbl = QLabel(result)
            result_lbl.setWordWrap(True)
            result_lbl.setStyleSheet(
                "color: #d1fae5; font-size: 13px; border: none; margin-top: 5px; font-family: Courier;"
            )
            widget_layout.addWidget(result_lbl)

        self.chat_layout.addWidget(widget_frame)

        QTimer.singleShot(
            50,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def submit_command(self):
        text = self.cmd_input.text().strip()
        if not text:
            return

        self.cmd_input.clear()
        self.append_chat_message("SYS.ADMIN", text, is_user=True)

        self.cmd_input.setEnabled(False)
        self.submit_btn.setEnabled(False)
        self.is_processing_anim = True

        if not self.headless and getattr(self, "inner_actor", None):
            self.inner_actor.GetProperty().SetColor((0.95, 0.25, 0.36))

        self.active_command_thread = CommandProcessorThread(text)
        self.active_command_thread.result_ready.connect(self.on_command_result)
        self.active_command_thread.start()

    def on_command_result(self, result: CommandResult, original_cmd: str):
        self.cmd_input.setEnabled(True)
        self.submit_btn.setEnabled(True)
        self.cmd_input.setFocus()
        self.is_processing_anim = False

        if (
            not self.headless
            and not self.is_lockdown
            and getattr(self, "inner_actor", None)
        ):
            self.inner_actor.GetProperty().SetColor((0.05, 0.64, 0.91))

        if result.text:
            self.append_chat_message("JARVIS.CORE", result.text, is_user=False)

    def on_event_received(self, event):
        msg = f"[{event.source}] {event.message}"

        if event.data:
            if "percent" in event.data:
                pass

            # --- LLM THINKING INDICATOR ---
            if event.data.get("type") == "llm_thinking":
                if event.data.get("state") == "start":
                    self.is_processing_anim = True
                    if (
                        not self.headless
                        and getattr(self, "inner_actor", None)
                        and not self._theater_mode
                    ):
                        self.inner_actor.GetProperty().SetColor((0.95, 0.25, 0.36))
                elif event.data.get("state") == "stop":
                    self.is_processing_anim = False
                    if (
                        not self.headless
                        and getattr(self, "inner_actor", None)
                        and not self._theater_mode
                    ):
                        self.inner_actor.GetProperty().SetColor((0.05, 0.64, 0.91))

            # --- VOICE INTERACTION INDICATOR ---
            if event.data.get("type") == "listening":
                if event.data.get("state") == "start":
                    self.listening_indicator.show()
                elif event.data.get("state") == "stop":
                    self.listening_indicator.hide()

            # --- TOOL CALL WIDGET INDICATOR ---
            if event.data.get("type") == "tool_call":
                tool_name = event.data.get("tool", "unknown_tool")
                args = event.data.get("args", {})
                self.append_tool_widget(tool_name, args)

            # --- BIOMETRIC SECURITY INDICATOR ---
            if event.data.get("type") == "security_alert":
                self.is_lockdown = True
                if (
                    not self.headless
                    and not self._theater_mode
                    and getattr(self, "inner_actor", None)
                ):
                    self.inner_actor.GetProperty().SetColor((1.0, 0.0, 0.0))
                    self.ring_actor.GetProperty().SetColor((1.0, 0.0, 0.0))
                    self.outer_actor.GetProperty().SetColor((1.0, 0.0, 0.0))

            if event.data.get("type") == "biometric_unlocked":
                self.is_lockdown = False
                if (
                    not self.headless
                    and not self._theater_mode
                    and getattr(self, "inner_actor", None)
                ):
                    self.plotter.set_background(
                        "#020617", top="#0f172a"
                    )  # Restore deep space
                    self.inner_actor.GetProperty().SetColor((0.05, 0.64, 0.91))
                    self.ring_actor.GetProperty().SetColor((0.05, 0.64, 0.91))
                    self.outer_actor.GetProperty().SetColor((0.22, 0.74, 0.97))

            if event.data.get("type") == "voice_interaction":
                query = event.data.get("query", "")
                response = event.data.get("response", "")
                if query:
                    self.append_chat_message("SYS.AUDIO", query, is_user=True)
                if response:
                    self.append_chat_message("JARVIS.CORE", response, is_user=False)

            # --- SUBAGENT SWARM INDICATORS ---
            if event.data.get("type") == "subagent_spawned":
                role = event.data.get("role", "UNKNOWN_AGENT")
                self.append_subagent_widget(role, "WORKING")

            if event.data.get("type") == "subagent_completed":
                role = event.data.get("role", "UNKNOWN_AGENT")
                result = event.data.get("result", "")
                self.append_subagent_widget(role, "COMPLETED", result)

            # --- THEATER CORE EVENTS ---
            if self._theater_mode and self._memory_theater:
                if event.data.get("type") == "theater_tick":
                    self._memory_theater.on_tick(event.data.get("positions", {}))
                elif event.data.get("type") == "node_event":
                    data_kwargs = event.data.copy()
                    data_kwargs.pop("type", None)
                    self._memory_theater.on_node_event(NodeEvent(**data_kwargs))

            # Allow recall via UI click to execute
            if event.data.get("type") == "recall_request":
                mem_id = event.data.get("memory_id")
                if mem_id is not None:
                    # In a real impl we might trigger a specific route,
                    # here we just trigger the command thread to handle it or fetch it.
                    from backend.modules.memory import get_engine

                    engine = get_engine()
                    c = engine.conn.cursor()
                    c.execute("SELECT content FROM memories WHERE id = ?", (mem_id,))
                    row = c.fetchone()
                    if row:
                        content = row["content"]
                        # Create command result mimicking recall
                        res = CommandResult(text=content, source="memory_theater")
                        self.on_command_result(res, "recall_memory")
                        try:
                            from backend.core.tts import speak

                            speak(content)
                        except Exception:
                            pass

        # Add to event ticker
        current_text = self.event_ticker.text()
        log_lines = current_text.split("\n")
        log_lines.insert(0, f"> {time.strftime('%H:%M:%S')} - {msg}")
        self.event_ticker.setText("\n".join(log_lines[:15]))

        if event.severity in (Severity.WARNING, Severity.ERROR):
            self.append_chat_message("SYS.ALERT", msg, is_user=False)

    def closeEvent(self, event):
        if not self.headless:
            self.plotter.close()
        super().closeEvent(event)



def run_gui():
    app = QApplication(sys.argv)
    window = JarvisNativeUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
