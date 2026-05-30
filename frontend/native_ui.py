import sys
import os
import time
import asyncio
import qdarktheme
import pyvista as pv
import numpy as np
import psutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QProgressBar,
    QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QFont, QCursor

from pyvistaqt import QtInteractor
from shared.event_bus import poll_event
from shared.schemas import CommandResult, Severity
from backend.core.router import process_command


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


class CommandProcessorThread(QThread):
    result_ready = pyqtSignal(object, str)

    def __init__(self, command_text: str):
        super().__init__()
        self.command_text = command_text

    def run(self):
        try:
            result = process_command(self.command_text)
            self.result_ready.emit(result, self.command_text)
            if result.text:
                try:
                    from backend.core.tts import speak
                    speak(result.text)
                except Exception:
                    pass
        except Exception as e:
            err_result = CommandResult(text=f"Command failed: {str(e)}", continue_loop=True, severity=Severity.ERROR)
            self.result_ready.emit(err_result, self.command_text)


class TelemetryThread(QThread):
    metrics_ready = pyqtSignal(dict)
    def run(self):
        while True:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.metrics_ready.emit({"cpu": cpu, "ram": ram})
            time.sleep(1)


# ---------------------------------------------------------
# Main JARVIS 3D Application
# ---------------------------------------------------------
class JarvisNativeUI(QMainWindow):
    def __init__(self, headless: bool = False):
        super().__init__()
        self.headless = headless
        self.setWindowTitle("JARVIS 2.0 - Core")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.resize(1500, 850)

        # For custom window dragging
        self._drag_pos = QPoint()

        # Apply global dark theme cleanly
        app = QApplication.instance()
        if app:
            app.setStyleSheet(qdarktheme.load_stylesheet("dark"))

        # Main Central Widget
        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("""
            QWidget#MainWidget {
                background-color: #020617;
                border: 1px solid #1e293b;
            }
        """)
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

    # --- Title Bar & Drag Logic ---
    def init_title_bar(self):
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(40)
        self.title_bar.setStyleSheet("background-color: #0f172a; border-bottom: 1px solid #1e293b;")
        
        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(15, 0, 15, 0)
        
        title_lbl = QLabel("JARVIS OS // NEXUS CORE")
        title_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-family: Courier; border: none;")
        layout.addWidget(title_lbl)
        
        layout.addStretch()
        
        self.listening_indicator = QLabel("🔴 LISTENING...")
        self.listening_indicator.setStyleSheet("color: #ef4444; font-weight: bold; font-family: Courier; border: none; padding-right: 15px;")
        self.listening_indicator.hide()
        layout.addWidget(self.listening_indicator)
        
        close_btn = QPushButton("X")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #94a3b8; border: none; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ef4444; color: white; border-radius: 4px;
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.main_layout.addWidget(self.title_bar)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.pos().y() < self.title_bar.height():
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()


    # --- Telemetry Sidebar ---
    def init_telemetry_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)
        self.sidebar.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        header = QLabel("SYSTEM TELEMETRY")
        header.setStyleSheet("color: #0ea5e9; font-weight: bold; font-family: Courier; border: none; font-size: 14px;")
        layout.addWidget(header)

        # CPU
        cpu_lbl = QLabel("CPU USAGE")
        cpu_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setTextVisible(False)
        self.cpu_bar.setFixedHeight(8)
        self.cpu_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #1e293b; border-radius: 4px; }
            QProgressBar::chunk { background-color: #38bdf8; border-radius: 4px; }
        """)
        self.cpu_val = QLabel("0%")
        self.cpu_val.setStyleSheet("color: white; border: none; font-size: 12px;")
        
        layout.addWidget(cpu_lbl)
        layout.addWidget(self.cpu_bar)
        layout.addWidget(self.cpu_val)

        # RAM
        ram_lbl = QLabel("MEMORY ALLOCATION")
        ram_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; border: none; margin-top: 10px;")
        self.ram_bar = QProgressBar()
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setFixedHeight(8)
        self.ram_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #1e293b; border-radius: 4px; }
            QProgressBar::chunk { background-color: #a855f7; border-radius: 4px; }
        """)
        self.ram_val = QLabel("0%")
        self.ram_val.setStyleSheet("color: white; border: none; font-size: 12px;")
        
        layout.addWidget(ram_lbl)
        layout.addWidget(self.ram_bar)
        layout.addWidget(self.ram_val)
        
        # Event Ticker
        layout.addStretch()
        ticker_hdr = QLabel("LIVE EVENT LOG")
        ticker_hdr.setStyleSheet("color: #0ea5e9; font-weight: bold; font-family: Courier; border: none; font-size: 12px;")
        layout.addWidget(ticker_hdr)
        
        self.event_ticker = QLabel("Awaiting events...")
        self.event_ticker.setStyleSheet("color: #64748b; font-size: 11px; border: none; font-family: Courier;")
        self.event_ticker.setWordWrap(True)
        self.event_ticker.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.event_ticker, stretch=1)

        self.content_layout.addWidget(self.sidebar)

    def update_telemetry(self, metrics: dict):
        cpu = metrics["cpu"]
        ram = metrics["ram"]
        self.cpu_bar.setValue(int(cpu))
        self.cpu_val.setText(f"{cpu}%")
        self.ram_bar.setValue(int(ram))
        self.ram_val.setText(f"{ram}%")

        if cpu > 80:
            self.cpu_bar.setStyleSheet("QProgressBar { border: none; background-color: #1e293b; border-radius: 4px; } QProgressBar::chunk { background-color: #ef4444; border-radius: 4px; }")
        else:
            self.cpu_bar.setStyleSheet("QProgressBar { border: none; background-color: #1e293b; border-radius: 4px; } QProgressBar::chunk { background-color: #38bdf8; border-radius: 4px; }")


    # --- 3D VTK Core ---
    def init_3d_core(self):
        self.left_frame = QFrame()
        self.left_frame.setStyleSheet("border: 1px solid #1e293b; border-radius: 8px;")
        self.left_layout = QVBoxLayout(self.left_frame)
        self.left_layout.setContentsMargins(2, 2, 2, 2)
        
        self.plotter = QtInteractor(self.left_frame)
        # Gradient background
        self.plotter.set_background("#020617", top="#0f172a") 
        self.plotter.enable_anti_aliasing()
        self.left_layout.addWidget(self.plotter.interactor)
        
        # Complex Geometry
        self.outer_cube = pv.Cube().scale([1.5, 1.5, 1.5])
        self.outer_sphere = pv.Sphere(radius=1.3, theta_resolution=30, phi_resolution=30)
        self.inner_sphere = pv.Sphere(radius=0.6, theta_resolution=25, phi_resolution=25)
        self.ring_geom = pv.ParametricTorus(ringradius=0.95, crosssectionradius=0.03)
        
        self.cube_actor = self.plotter.add_mesh(self.outer_cube, style="wireframe", color="#1e293b", opacity=0.3)
        self.outer_actor = self.plotter.add_mesh(self.outer_sphere, color="#38bdf8", style="wireframe", line_width=1.5, opacity=0.15)
        self.inner_actor = self.plotter.add_mesh(self.inner_sphere, color="#0ea5e9", style="surface", opacity=0.8, lighting=True, specular=0.5)
        self.ring_actor = self.plotter.add_mesh(self.ring_geom, color="#0ea5e9", style="wireframe", line_width=2, opacity=0.5)
        
        self.content_layout.addWidget(self.left_frame, stretch=5)
        
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.animate_core)
        self.anim_timer.start(40) # 25fps
        self.start_time = time.time()
        self.is_processing_anim = False
        self.is_lockdown = False

    def animate_core(self):
        self.cube_actor.RotateX(0.1)
        self.cube_actor.RotateY(-0.1)
        self.outer_actor.RotateY(0.5)
        self.inner_actor.RotateZ(-0.4)
        self.ring_actor.RotateZ(1.5)
        self.ring_actor.RotateY(0.5)
        
        base_opacity = 0.6
        pulse_speed = 3
        if self.is_processing_anim:
            pulse_speed = 12
        if self.is_lockdown:
            pulse_speed = 25 # frantic pulsing
            
            # Flashing red background effect
            if not self.headless:
                if int(time.time() * 6) % 2 == 0:
                    self.plotter.set_background("#450a0a", top="#7f1d1d")
                else:
                    self.plotter.set_background("#200505", top="#450a0a")
        
        opacity = base_opacity + 0.2 * np.sin((time.time() - self.start_time) * pulse_speed)
        if not self.headless:
            self.inner_actor.GetProperty().SetOpacity(float(opacity))
        self.plotter.interactor.Render()

    # --- Holographic Chat Dashboard ---
    def init_dashboard(self):
        self.right_frame = QFrame()
        self.right_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        self.right_layout = QVBoxLayout(self.right_frame)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(15)

        # Chat Feed
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: 1px solid #1e293b; border-radius: 8px; background-color: #0f172a; }
            QScrollBar:vertical { background: #0f172a; width: 8px; }
            QScrollBar::handle:vertical { background: #334155; border-radius: 4px; }
        """)
        
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(15)
        self.chat_layout.setContentsMargins(15, 15, 15, 15)
        
        self.scroll_area.setWidget(self.chat_container)
        self.right_layout.addWidget(self.scroll_area, stretch=1)
        
        # Futuristic Input Deck
        self.input_deck = QFrame()
        self.input_deck.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        deck_layout = QHBoxLayout(self.input_deck)
        deck_layout.setContentsMargins(10, 10, 10, 10)
        
        sys_lbl = QLabel("[SYS.ADMIN] >")
        sys_lbl.setStyleSheet("color: #0ea5e9; font-weight: bold; font-family: Courier; border: none;")
        deck_layout.addWidget(sys_lbl)
        
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Transmit command...")
        self.cmd_input.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 14px;
                font-family: Courier;
            }
        """)
        self.cmd_input.returnPressed.connect(self.submit_command)
        deck_layout.addWidget(self.cmd_input, stretch=1)
        
        self.submit_btn = QPushButton("TX_SEND")
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: #020617;
                border-radius: 4px;
                padding: 8px 15px;
                font-weight: bold;
                font-family: Courier;
            }
            QPushButton:hover {
                background-color: #38bdf8;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #94a3b8;
            }
        """)
        self.submit_btn.clicked.connect(self.submit_command)
        deck_layout.addWidget(self.submit_btn)
        
        self.right_layout.addWidget(self.input_deck)
        self.content_layout.addWidget(self.right_frame, stretch=3)

    def append_chat_message(self, sender: str, text: str, is_user: bool = False):
        msg_frame = QFrame()
        msg_layout = QVBoxLayout(msg_frame)
        msg_layout.setContentsMargins(15, 12, 15, 12)
        
        if is_user:
            msg_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(14, 165, 233, 0.1);
                    border: 1px solid rgba(14, 165, 233, 0.3);
                    border-left: 4px solid #0ea5e9;
                    border-radius: 6px;
                }
            """)
            sender_color = "#38bdf8"
        else:
            msg_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(30, 41, 59, 0.5);
                    border: 1px solid #1e293b;
                    border-right: 4px solid #a855f7;
                    border-radius: 6px;
                }
            """)
            sender_color = "#a855f7"
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        sender_lbl = QLabel(sender)
        sender_lbl.setStyleSheet(f"color: {sender_color}; font-weight: bold; font-size: 11px; border: none; font-family: Courier;")
        
        time_lbl = QLabel(time.strftime("%H:%M:%S"))
        time_lbl.setStyleSheet("color: #64748b; font-size: 10px; border: none; font-family: Courier;")
        
        header_layout.addWidget(sender_lbl)
        header_layout.addStretch()
        header_layout.addWidget(time_lbl)
        
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet("color: #f8fafc; font-size: 14px; border: none; margin-top: 5px;")
        
        msg_layout.addLayout(header_layout)
        msg_layout.addWidget(text_lbl)
        
        self.chat_layout.addWidget(msg_frame)
        
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def append_tool_widget(self, tool_name: str, args: dict):
        widget_frame = QFrame()
        widget_layout = QVBoxLayout(widget_frame)
        widget_layout.setContentsMargins(15, 12, 15, 12)
        
        # Tool Widget Styling (Glowing Amber/Yellow)
        widget_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(245, 158, 11, 0.1);
                border: 1px solid rgba(245, 158, 11, 0.4);
                border-left: 4px solid #f59e0b;
                border-radius: 8px;
            }
        """)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_lbl = QLabel("⚙️ TOOL EXECUTING")
        icon_lbl.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px; border: none; font-family: Courier;")
        
        name_lbl = QLabel(f"[{tool_name.upper()}]")
        name_lbl.setStyleSheet("color: #fcd34d; font-weight: bold; font-size: 11px; border: none; font-family: Courier;")
        
        header_layout.addWidget(icon_lbl)
        header_layout.addStretch()
        header_layout.addWidget(name_lbl)
        
        args_text = "\\n".join(f"{k}: {v}" for k, v in args.items()) if args else "No arguments."
        args_lbl = QLabel(args_text)
        args_lbl.setWordWrap(True)
        args_lbl.setStyleSheet("color: #fef3c7; font-size: 12px; border: none; margin-top: 5px; font-family: Courier;")
        
        widget_layout.addLayout(header_layout)
        widget_layout.addWidget(args_lbl)
        
        self.chat_layout.addWidget(widget_frame)
        
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

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
        icon_lbl.setStyleSheet(f"color: {icon_color}; font-weight: bold; font-size: 11px; border: none; font-family: Courier;")
        
        name_lbl = QLabel(f"[{role.upper()}]")
        name_lbl.setStyleSheet("color: #6ee7b7; font-weight: bold; font-size: 11px; border: none; font-family: Courier;")
        
        header_layout.addWidget(icon_lbl)
        header_layout.addStretch()
        header_layout.addWidget(name_lbl)
        
        widget_layout.addLayout(header_layout)
        
        if result:
            result_lbl = QLabel(result)
            result_lbl.setWordWrap(True)
            result_lbl.setStyleSheet("color: #d1fae5; font-size: 13px; border: none; margin-top: 5px; font-family: Courier;")
            widget_layout.addWidget(result_lbl)
            
        self.chat_layout.addWidget(widget_frame)
        
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def submit_command(self):
        text = self.cmd_input.text().strip()
        if not text: return
        
        self.cmd_input.clear()
        self.append_chat_message("SYS.ADMIN", text, is_user=True)
        
        self.cmd_input.setEnabled(False)
        self.submit_btn.setEnabled(False)
        self.is_processing_anim = True
        
        if not self.headless:
            self.inner_actor.GetProperty().SetColor((0.95, 0.25, 0.36)) 
        
        self.active_command_thread = CommandProcessorThread(text)
        self.active_command_thread.result_ready.connect(self.on_command_result)
        self.active_command_thread.start()

    def on_command_result(self, result: CommandResult, original_cmd: str):
        self.cmd_input.setEnabled(True)
        self.submit_btn.setEnabled(True)
        self.cmd_input.setFocus()
        self.is_processing_anim = False
        
        if not self.headless and not self.is_lockdown:
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
                    if not self.headless:
                        self.inner_actor.GetProperty().SetColor((0.95, 0.25, 0.36)) 
                elif event.data.get("state") == "stop":
                    self.is_processing_anim = False
                    if not self.headless:
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
                if not self.headless:
                    self.inner_actor.GetProperty().SetColor((1.0, 0.0, 0.0))
                    self.ring_actor.GetProperty().SetColor((1.0, 0.0, 0.0))
                    self.outer_actor.GetProperty().SetColor((1.0, 0.0, 0.0))
                    
            if event.data.get("type") == "biometric_unlocked":
                self.is_lockdown = False
                if not self.headless:
                    self.plotter.set_background("#020617", top="#0f172a") # Restore deep space
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

        # Add to event ticker
        current_text = self.event_ticker.text()
        log_lines = current_text.split('\n')
        log_lines.insert(0, f"> {time.strftime('%H:%M:%S')} - {msg}")
        self.event_ticker.setText('\n'.join(log_lines[:15]))

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
