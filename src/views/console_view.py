from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import QTimer
from src.model.log_status import LogStatus
from src.controller.event_bus import EventBus

class DebugConsole(QTextEdit):
    """Simple debug console widget.

    High-level: this widget should subscribe to the application's EventBus
    and append human-readable log lines for incoming events. The actual
    subscription and asyncio/Qt coordination will be implemented later.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.event_bus = EventBus()
        self.event_bus.subscribe("log", self.append_log)
        

    def append_log(self, message: str):
        """Append a log message to the console."""
        formatted_text = f"[{self.get_current_time()}] {message}"
        self.append(formatted_text)

    def get_current_time(self) -> str:
        """Utility to get current time as a string for log timestamps."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")