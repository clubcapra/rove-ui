from __future__ import annotations

import random

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class BitmapPlaceholder:
    def __init__(self, name: str, config: dict | None = None):
        self.name = name
        self.config = config or {}
        self._widget: QWidget | None = None
        self._label: QLabel | None = None
        self._nam: QNetworkAccessManager | None = None
        self._timer: QTimer | None = None
        self._pending: bool = False
        self._connection_logged: bool = False

    def build(self) -> None:
        if self._widget is not None:
            return

        self._widget = QWidget()
        self._widget.setMinimumSize(320, 220)
        self._widget.setCursor(Qt.CursorShape.CrossCursor)

        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = QLabel(self._widget)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setScaledContents(True)
        layout.addWidget(self._label)

        source = str(self.config.get("source", "")).strip()
        if source:
            self._label.setPixmap(self._make_placeholder_pixmap(320, 220))
            self._nam = QNetworkAccessManager(self._widget)
            self._nam.finished.connect(self._on_reply)

            self._timer = QTimer(self._widget)
            self._timer.timeout.connect(self._fetch)
            interval_ms = max(50, int(self.config.get("poll_interval_ms", 200)))
            self._timer.start(interval_ms)
            self._fetch()
        else:
            self._label.setPixmap(self._make_placeholder_pixmap(640, 420))

    def _fetch(self) -> None:
        if self._pending or self._nam is None:
            return
        source = str(self.config.get("source", "")).strip()
        if not source:
            return
        request = QNetworkRequest(QUrl(source))
        request.setRawHeader(b"Cache-Control", b"no-cache")
        self._nam.get(request)
        self._pending = True

    def _on_reply(self, reply: QNetworkReply) -> None:
        self._pending = False
        if reply.error() == QNetworkReply.NetworkError.NoError:
            self._connection_logged = False
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data) and not pixmap.isNull() and self._label:
                self._label.setPixmap(pixmap)
        else:
            if not self._connection_logged:
                source = str(self.config.get("source", "")).strip()
                print(f"[BitmapPlaceholder] Impossible de se connecter à {source} : {reply.errorString()}")
                self._connection_logged = True
        reply.deleteLater()

    def _make_placeholder_pixmap(self, width: int, height: int) -> QPixmap:
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
