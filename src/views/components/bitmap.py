from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.controller.event_bus import EventBus


class _ClickableLabel(QLabel):
    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._last_click_ms: int = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from PySide6.QtCore import QDateTime
            now = QDateTime.currentMSecsSinceEpoch()
            if now - self._last_click_ms < 300:  # debounce 300ms
                super().mousePressEvent(event)
                return
            self._last_click_ms = now
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                nx = event.position().x() / w
                ny = event.position().y() / h
                self._on_click(nx, ny)
        super().mousePressEvent(event)


class Bitmap:
    def __init__(self, name: str, config: dict | None = None, event_bus: EventBus | None = None):
        self.name = name
        self.config = config or {}
        self.event_bus = event_bus or EventBus()
        self._widget: QWidget | None = None
        self._label: _ClickableLabel | None = None
        self._nam: QNetworkAccessManager | None = None
        self._timer: QTimer | None = None
        self._pending: bool = False
        self._connection_logged: bool = False
        self._robot_lat: float | None = None
        self._robot_lng: float | None = None
        self._robot_yaw: float = 0.0  # degrés

    def build(self) -> None:
        if self._widget is not None:
            return

        self._widget = QWidget()
        self._widget.setMinimumSize(320, 220)
        self._widget.setCursor(Qt.CursorShape.CrossCursor)

        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = _ClickableLabel(self._handle_click, self._widget)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setScaledContents(True)
        layout.addWidget(self._label)

        self._register_gps_tracking()

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

    def _register_gps_tracking(self) -> None:
        lat_topic = str(self.config.get("gps_lat_topic", "gnss.latitude")).strip()
        lng_topic = str(self.config.get("gps_lng_topic", "gnss.longitude")).strip()
        yaw_topic = str(self.config.get("gps_yaw_topic", "gnss.yaw")).strip()

        def _on_lat(v):
            try: self._robot_lat = float(v)
            except (TypeError, ValueError): pass
        def _on_lng(v):
            try: self._robot_lng = float(v)
            except (TypeError, ValueError): pass
        def _on_yaw(v):
            try: self._robot_yaw = float(v)
            except (TypeError, ValueError): pass

        self.event_bus.subscribe(lat_topic, _on_lat)
        self.event_bus.subscribe(lng_topic, _on_lng)
        self.event_bus.subscribe(yaw_topic, _on_yaw)

    def _handle_click(self, nx: float, ny: float) -> None:
        radius_x = float(self.config.get("cornerPositionWidth",  1.0)) / 2.0
        radius_y = float(self.config.get("cornerPositionHeight", 1.0)) / 2.0
        # (0,0) = centre, x positif = droite, y positif = haut
        local_x = (nx - 0.5) * 2.0 * radius_x
        local_y = (0.5 - ny) * 2.0 * radius_y

        click_topic = str(self.config.get("click_topic", "costmap.click")).strip()
        payload: dict = {"x": round(local_x, 3), "y": round(local_y, 3)}

        poi_topic = str(self.config.get("poi_topic", "")).strip()
        if poi_topic:
            # TODO: retirer le fallback (0, 0) une fois le GPS fonctionnel — garder seulement le bloc "if has_gps"
            has_gps = self._robot_lat is not None and self._robot_lng is not None
            robot_lat = self._robot_lat if has_gps else 0.0
            robot_lng = self._robot_lng if has_gps else 0.0

            # Rotation du repère robot → repère monde (Nord/Est) via le yaw
            yaw_rad = math.radians(self._robot_yaw)
            east  = local_x * math.cos(yaw_rad) - local_y * math.sin(yaw_rad)
            north = local_x * math.sin(yaw_rad) + local_y * math.cos(yaw_rad)

            # Conversion mètres → degrés
            # TODO: enlever ce bloc et ne publier que si has_gps quand le GPS sera fiable
            ref_lat = robot_lat if has_gps else 45.5017  # latitude de référence pour cos(lat) si pas de GPS
            poi_lat = robot_lat + north / 111_111.0
            poi_lng = robot_lng + east  / (111_111.0 * math.cos(math.radians(ref_lat)))

            payload["lat"] = round(poi_lat, 8)
            payload["lng"] = round(poi_lng, 8)
            self.event_bus.publish_sync(poi_topic, {"lat": poi_lat, "lng": poi_lng, "label": f"{poi_lat:.5f},{poi_lng:.5f}"})

        self.event_bus.publish_sync(click_topic, payload)
        self.event_bus.publish_sync("log", f"[Bitmap:{self.name}] clic → local=({payload['x']},{payload['y']}) gps={payload.get('lat','?')},{payload.get('lng','?')}")

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
                print(f"[Bitmap] Impossible de se connecter à {source} : {reply.errorString()}")
                self._connection_logged = True
        reply.deleteLater()

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]
