from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class BitmapPlaceholder:
    def __init__(self, name: str, config: dict | None = None):
        self.name = name
        self.config = config or {}
        self._widget: QWidget | None = None

    def build(self) -> None:
        if self._widget is not None:
            return

        self._widget = QWidget()
        self._widget.setMinimumSize(320, 220)

        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(self._widget)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(self._make_pixmap(640, 420))
        label.setScaledContents(True)
        layout.addWidget(label)

    def _make_pixmap(self, width: int, height: int) -> QPixmap:
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#0f172a"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        random.seed(42)
        for _ in range(90):
            color = QColor(
                random.randint(80, 220),
                random.randint(80, 220),
                random.randint(80, 220),
                random.randint(90, 170),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            x = random.randint(0, width)
            y = random.randint(0, height)
            radius = random.randint(18, 90)
            painter.drawEllipse(x, y, radius, radius)

        painter.setPen(QPen(QColor("#e2e8f0"), 2))
        painter.setFont(QFont("Sans Serif", 18, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, self.name)
        painter.end()
        return pixmap

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]