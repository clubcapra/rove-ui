"""A full-page panic/exit control.

The app runs full-screen (``showFullScreen``) with no window chrome, so there
is no OS-level way to close it. This widget provides a big red button that
shuts the whole application down cleanly. It's a two-tap confirm so an
accidental brush of the touchscreen doesn't kill the UI mid-operation.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.controller.event_bus import EventBus
from src.views import theme

_CONFIRM_TIMEOUT_MS = 4000


class QuitWidget(QWidget):
    """Big red STOP & EXIT button that quits the application."""

    def __init__(self, name: str = "quit", data: dict | None = None,
                 event_bus: EventBus | None = None, parent=None) -> None:
        super().__init__(parent)
        self._cfg = data or {}
        self.event_bus = event_bus or EventBus()
        self._armed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._disarm)
        self._build_ui()

    def build(self) -> None:  # parity with other components' build() API
        pass

    def get_widget(self) -> QWidget:
        return self

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG_PANEL}; color: {theme.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)
        root.addStretch()

        title = QLabel("SHUT DOWN INTERFACE")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 16px; font-family: 'Courier New'; "
            "letter-spacing: 3px; background: transparent;"
        )
        root.addWidget(title)

        self._btn = QPushButton("⏻  STOP & EXIT")
        self._btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._btn.setMinimumHeight(220)
        self._btn.clicked.connect(self._on_click)
        self._style_btn(armed=False)
        root.addWidget(self._btn, 1)

        self._hint = QLabel("")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 12px; font-family: 'Courier New'; "
            "background: transparent;"
        )
        root.addWidget(self._hint)
        root.addStretch()

    def _style_btn(self, armed: bool) -> None:
        accent = "#ffaa00" if armed else "#ff2222"
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_DARK}; color: {accent}; "
            f"border: 4px solid {accent}; border-radius: 8px; "
            f"font-size: 42px; font-weight: bold; font-family: 'Courier New'; "
            "letter-spacing: 4px; }"
            f"QPushButton:hover {{ background: {accent}; color: {theme.BG_DARK}; }}"
            f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
        )

    # ------------------------------------------------------------------

    def _on_click(self) -> None:
        if not self._armed:
            self._armed = True
            self._btn.setText("⚠  TAP AGAIN TO EXIT")
            self._style_btn(armed=True)
            self._hint.setText(f"Cancels in {_CONFIRM_TIMEOUT_MS // 1000}s")
            self._timer.start(_CONFIRM_TIMEOUT_MS)
            return
        self._quit()

    def _disarm(self) -> None:
        self._armed = False
        self._btn.setText("⏻  STOP & EXIT")
        self._style_btn(armed=False)
        self._hint.setText("")

    def _quit(self) -> None:
        self._hint.setText("shutting down…")
        app = QApplication.instance()
        if app is not None:
            # Close all windows first so each window's closeEvent runs
            # (stops UDP/ROS2/HTTP clients and the teleop controller thread),
            # then exit the event loop.
            app.closeAllWindows()
            app.quit()
