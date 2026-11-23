import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

from frontend.native_ui import JarvisNativeUI
from unittest.mock import patch

def test():
    app = QApplication(sys.argv)

    def mock_take_command(timeout=10):
        print("Mock mic listening...")
        time.sleep(0.5)
        return "testing voice input"

    with patch('backend.core.stt.take_command', mock_take_command):
        # Must run normally (not headless) to fully init GUI components?
        # Actually JarvisNativeUI tries to initialize everything.
        # Let's mock the event bus or router if needed, or just let it run.
        ui = JarvisNativeUI()
        print("UI Initialized.")
        
        print("Triggering arc reactor click...")
        ui.on_pick((0,0,0))
        
        print("Is listening immediately after click:", getattr(ui, 'is_listening', False))
        
        timeout_t = time.time() + 2
        while time.time() < timeout_t and ui.is_listening:
            QCoreApplication.processEvents()
            time.sleep(0.05)
            
        print("Is listening after wait:", getattr(ui, 'is_listening', False))

if __name__ == "__main__":
    test()
