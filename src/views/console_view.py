from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Signal
from src.model.log_status import LogStatus
from src.controller.event_bus import EventBus

class DebugConsole(QTextEdit):
    """Simple debug console widget.

    High-level: this widget should subscribe to the application's EventBus
    and append human-readable log lines for incoming events. The actual
    subscription and asyncio/Qt coordination will be implemented later.
    """

    append_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.event_bus = EventBus()
        self.append_requested.connect(self._append_log_on_ui_thread)
        self.event_bus.subscribe("log", self.append_log)
        

    def append_log(self, message: str):
        self.append_requested.emit(message)

    def _append_log_on_ui_thread(self, message: str):
        """Append a log message to the console."""
        formatted_text = f"[{self.get_current_time()}] {message}"
        self.append(formatted_text)

    def get_current_time(self) -> str:
        """Utility to get current time as a string for log timestamps."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")