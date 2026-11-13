from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTextEdit

from src.controller.event_bus import EventBus
from src.views import theme


class DebugConsole(QTextEdit):
    append_requested = Signal(str)

    _STYLE = f"""
        QTextEdit {{
            background: {theme.BG_DEEP};
            color: {theme.TEXT};
            font-family: {theme.FONT_MONO};
            font-size: 11px;
            border: none;
            padding: 6px 10px;
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(self._STYLE)
        self.event_bus = EventBus()
        self.append_requested.connect(self._do_append)
        self.event_bus.subscribe("log", self.append_log)

    def append_log(self, message: str) -> None:
        self.append_requested.emit(str(message))

    def _do_append(self, message: str) -> None:
        ts   = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        # Escape HTML special chars
        msg  = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        line = (
            f'<span style="color:{theme.AMBER};font-weight:700;">[{ts}]</span>'
            f'&nbsp;<span style="color:{theme.TEXT};">{msg}</span>'
        )
        self.append(line)
        # Auto-scroll to bottom
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())
