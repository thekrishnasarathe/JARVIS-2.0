"""
Facade module for backward compatibility.
"""
from backend.core.router import process_command
from frontend.threads import EventBusThread, CommandProcessorThread, TelemetryThread, VoiceInputThread
from frontend.memory_theater import MemoryTheater
from frontend.widgets import CompatLabel, TechHeaderWidget, SubsystemBadge, ChatBubbleWidget, AdvancedCpuWidget, HUDLabel, CircularCpuWidget
from frontend.main_window import JarvisNativeUI, run_gui

if __name__ == '__main__':
    run_gui()
