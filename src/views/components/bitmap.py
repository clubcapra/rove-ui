from __future__ import annotations

import math
import random

from PySide6.QtCore import QDateTime, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from src.controller.event_bus import EventBus

_ACCENT = "#f59e0b"
_PANEL  = "#1e293b"


# ── Altitude picker dialog ─────────────────────────────────────────────────────

class _AltitudePicker(QDialog):
    """Modal popup to pick POI altitude (0–5 m, precision 0.01 m)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Altitude du point")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setFixedWidth(200)
        self._altitude = 0.0

        self.setStyleSheet(f"""
            QDialog {{
                background: {_PANEL};
                border: 2px solid {_ACCENT};
                border-radius: 10px;
            }}
            QLabel {{ color: #f1f5f9; background: transparent; }}
            QPushButton {{
                background: #334155; color: #f1f5f9;
                border: 1px solid #475569; border-radius: 5px;
                padding: 5px 14px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #475569; }}
            QPushButton#ok {{
                background: {_ACCENT}; color: #1e293b;
                font-weight: 700; border: none;
            }}
            QPushButton#ok:hover {{ background: #fbbf24; }}
            QSlider::groove:vertical {{
                background: #334155; width: 8px; border-radius: 4px; margin: 0 8px;
            }}
            QSlider::handle:vertical {{
                background: {_ACCENT};
                height: 20px; width: 20px;
                margin: 0 -6px;
                border-radius: 10px;
                border: 2px solid {_PANEL};
            }}
            QSlider::sub-page:vertical {{
                background: {_ACCENT}; border-radius: 4px; margin: 0 8px;
            }}
            QSlider::add-page:vertical {{
                background: #334155; border-radius: 4px; margin: 0 8px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # Title
        title = QLabel("Altitude du POI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {_ACCENT};")
        outer.addWidget(title)

        # Big value label
        self._val_label = QLabel("0.00 m")
        self._val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_label.setStyleSheet(
            "font-size: 32px; font-weight: 700; letter-spacing: 1px; padding: 2px 0;"
        )
        outer.addWidget(self._val_label)

        # Slider area: tick labels + slider side by side
        slider_row = QHBoxLayout()
        slider_row.setSpacing(4)

        # Left tick labels (5→0 top to bottom, 6 equally spaced)
        tick_col = QVBoxLayout()
        tick_col.setContentsMargins(0, 0, 0, 0)
        tick_col.setSpacing(0)
        for txt in ("5", "4", "3", "2", "1", "0"):
            lbl = QLabel(txt)
            lbl.setStyleSheet("font-size: 9px; color: #64748b;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tick_col.addWidget(lbl, stretch=1)
        slider_row.addLayout(tick_col)

        lbl_m = QLabel("m")
        lbl_m.setStyleSheet("font-size: 9px; color: #475569;")
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignTop)
        slider_row.addWidget(lbl_m)

        # Vertical slider: 0 = 0.00 m (bottom) → 500 = 5.00 m (top)
        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(0, 500)
        self._slider.setValue(0)
        self._slider.setMinimumHeight(180)
        self._slider.setSingleStep(1)    # 0.01 m
        self._slider.setPageStep(10)     # 0.10 m
        self._slider.setTickInterval(100)
        self._slider.setTickPosition(QSlider.TickPosition.TicksLeft)
        self._slider.valueChanged.connect(self._on_slider)
        slider_row.addWidget(self._slider)
        outer.addLayout(slider_row)

        # Precision hint
        hint = QLabel("← ↑↓ 0.01 m  |  PgUp/Dn 0.10 m")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 8px; color: #475569;")
        outer.addWidget(hint)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("✓ OK")
        ok_btn.setObjectName("ok")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        outer.addLayout(btn_row)

    def _on_slider(self, value: int) -> None:
        self._altitude = value / 100.0
        self._val_label.setText(f"{self._altitude:.2f} m")

    def altitude(self) -> float:
        return self._altitude


# ── Clickable label (with debounce) ───────────────────────────────────────────

class _ClickableLabel(QLabel):
    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._last_click_ms: int = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            now = QDateTime.currentMSecsSinceEpoch()
            if now - self._last_click_ms < 300:
                super().mousePressEvent(event)
                return
            self._last_click_ms = now
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                nx = event.position().x() / w
                ny = event.position().y() / h
                self._on_click(nx, ny)
        super().mousePressEvent(event)


# ── Bitmap widget ──────────────────────────────────────────────────────────────

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

        # GPS state
        self._robot_lat: float | None = None
        self._robot_lng: float | None = None
        self._robot_yaw: float = 0.0        # degrés (heading from North, clockwise)

        # Overlay state
        self._raw_pixmap: QPixmap | None = None
        self._pois: list[dict] = []         # {"nx", "ny", "alt", "label"}
        self._poi_seq: int = 0

    # ── Build ──────────────────────────────────────────────────────────────────

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
            self._raw_pixmap = self._make_placeholder_pixmap(640, 420)
            self._update_display()

    # ── GPS tracking ───────────────────────────────────────────────────────────

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
            try:
                self._robot_yaw = float(v)
                self._update_display()      # refresh cursor heading
            except (TypeError, ValueError):
                pass

        self.event_bus.subscribe(lat_topic, _on_lat)
        self.event_bus.subscribe(lng_topic, _on_lng)
        self.event_bus.subscribe(yaw_topic, _on_yaw)

    # ── Click → altitude picker → POI ─────────────────────────────────────────

    def _handle_click(self, nx: float, ny: float) -> None:
        picker = _AltitudePicker(self._widget)

        # Centre the picker on the bitmap widget
        if self._widget:
            center = self._widget.mapToGlobal(self._widget.rect().center())
            picker.adjustSize()
            picker.move(
                center.x() - picker.width()  // 2,
                center.y() - picker.height() // 2,
            )

        if picker.exec() != QDialog.DialogCode.Accepted:
            return

        altitude = picker.altitude()

        radius_x = float(self.config.get("cornerPositionWidth",  1.0)) / 2.0
        radius_y = float(self.config.get("cornerPositionHeight", 1.0)) / 2.0
        local_x = (nx - 0.5) * 2.0 * radius_x
        local_y = (0.5 - ny) * 2.0 * radius_y

        payload: dict = {
            "x": round(local_x, 3),
            "y": round(local_y, 3),
            "z": round(altitude, 2),
        }

        poi_topic = str(self.config.get("poi_topic", "")).strip()
        if poi_topic:
            # TODO: retirer le fallback (0, 0) quand le GPS sera fiable
            has_gps    = self._robot_lat is not None and self._robot_lng is not None
            robot_lat  = self._robot_lat if has_gps else 0.0
            robot_lng  = self._robot_lng if has_gps else 0.0

            yaw_rad = math.radians(self._robot_yaw)
            east    = local_x * math.cos(yaw_rad) - local_y * math.sin(yaw_rad)
            north   = local_x * math.sin(yaw_rad) + local_y * math.cos(yaw_rad)

            ref_lat = robot_lat if has_gps else 45.5017
            poi_lat = robot_lat + north / 111_111.0
            poi_lng = robot_lng + east  / (111_111.0 * math.cos(math.radians(ref_lat)))

            payload["lat"] = round(poi_lat, 8)
            payload["lng"] = round(poi_lng, 8)

            self._poi_seq += 1
            label = f"#{self._poi_seq}"
            self.event_bus.publish_sync(
                poi_topic,
                {"lat": poi_lat, "lng": poi_lng, "label": label, "alt": altitude},
            )

            # Overlay marker
            self._pois.append({"nx": nx, "ny": ny, "alt": altitude, "label": label})
            self._update_display()

        click_topic = str(self.config.get("click_topic", "costmap.click")).strip()
        self.event_bus.publish_sync(click_topic, payload)
        self.event_bus.publish_sync(
            "log",
            f"[Bitmap:{self.name}] POI {self._poi_seq} → "
            f"local=({payload['x']},{payload['y']}) alt={altitude:.2f}m "
            f"gps={payload.get('lat','?')},{payload.get('lng','?')}",
        )

    # ── Overlay rendering ──────────────────────────────────────────────────────

    def _update_display(self) -> None:
        if self._raw_pixmap is None or self._raw_pixmap.isNull() or self._label is None:
            return
        result = self._raw_pixmap.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = result.width(), result.height()
        self._draw_pois(painter, w, h)
        self._draw_robot_cursor(painter, w // 2, h // 2, self._robot_yaw, min(w, h) // 10)
        painter.end()
        self._label.setPixmap(result)

    def _draw_robot_cursor(
        self, painter: QPainter, cx: int, cy: int, yaw_deg: float, size: int
    ) -> None:
        """Arrow centred at (cx, cy) pointing in the heading direction."""
        painter.save()
        painter.translate(cx, cy)
        # QPainter.rotate(deg) is clockwise; 0° = arrow tip pointing UP = North
        painter.rotate(yaw_deg)

        # Translucent halo
        ring_r = int(size * 1.15)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawEllipse(-ring_r, -ring_r, ring_r * 2, ring_r * 2)

        # Arrow triangle (tip UP = North when yaw=0)
        tip_y   = -int(size * 0.85)
        base_y  =  int(size * 0.55)
        base_hw =  int(size * 0.45)
        arrow = QPolygonF([
            QPointF(0,       tip_y),
            QPointF(-base_hw, base_y),
            QPointF(base_hw,  base_y),
        ])
        painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
        painter.setBrush(QColor(34, 197, 94, 230))
        painter.drawPolygon(arrow)

        # Red dot at exact robot position
        dot_r = max(3, size // 7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(239, 68, 68, 240))
        painter.drawEllipse(-dot_r, -dot_r, dot_r * 2, dot_r * 2)

        painter.restore()

    def _draw_pois(self, painter: QPainter, w: int, h: int) -> None:
        r = max(7, min(w, h) // 40)
        font_size = max(7, min(w, h) // 55)
        painter.setFont(QFont("Sans Serif", font_size, QFont.Weight.Bold))

        for poi in self._pois:
            px = int(poi["nx"] * w)
            py = int(poi["ny"] * h)

            # Pin circle — golden with dark border
            painter.setPen(QPen(QColor("#78350f"), 2))
            painter.setBrush(QColor(245, 158, 11, 220))
            painter.drawEllipse(px - r, py - r, r * 2, r * 2)

            # Pin stem
            stem = max(3, r // 2)
            painter.setPen(QPen(QColor("#f59e0b"), max(2, stem // 2)))
            painter.drawLine(px, py + r, px, py + r + stem)

            # White centre dot
            cr = max(2, r // 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(px - cr, py - cr, cr * 2, cr * 2)

            # Label + altitude (shadow then white)
            text = f"{poi['label']}  {poi['alt']:.2f} m"
            tx, ty = px + r + 3, py + font_size // 2
            painter.setPen(QPen(QColor(0, 0, 0, 160), 1))
            painter.drawText(tx + 1, ty + 1, text)
            painter.setPen(QPen(QColor("#fef3c7"), 1))
            painter.drawText(tx, ty, text)

    # ── Placeholder ────────────────────────────────────────────────────────────

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
            painter.drawEllipse(
                random.randint(0, width),
                random.randint(0, height),
                random.randint(18, 90),
                random.randint(18, 90),
            )
        painter.setPen(QPen(QColor("#e2e8f0"), 2))
        painter.setFont(QFont("Sans Serif", 18, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, self.name)
        painter.end()
        return pixmap

    # ── Network ────────────────────────────────────────────────────────────────

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
            pix = QPixmap()
            if pix.loadFromData(data) and not pix.isNull():
                self._raw_pixmap = pix
                self._update_display()
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
