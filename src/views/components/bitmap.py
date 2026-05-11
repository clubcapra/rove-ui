from __future__ import annotations

import base64
import math
import random
import tempfile
import os
from pathlib import Path

from PySide6.QtCore import QDateTime, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtNetwork import (
    QHttpMultiPart, QHttpPart,
    QNetworkAccessManager, QNetworkReply, QNetworkRequest,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from src.controller.event_bus import EventBus

_ACCENT = "#eb4034"
_PANEL  = "#1c1c1b"


# ── Altitude picker dialog ─────────────────────────────────────────────────────

class _AltitudePicker(QDialog):
    """Modal popup to pick POI altitude (0–5 m, precision 0.01 m)."""

    def __init__(self, event_bus: EventBus, ocr_url: str, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._ocr_url   = ocr_url
        self.setWindowTitle("Altitude du point")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setFixedWidth(224)
        self._altitude = 0.0
        self._photo_data_url: str | None = None
        self._nam_ocr: QNetworkAccessManager | None = None

        self.setStyleSheet(f"""
            QDialog {{
                background: {_PANEL};
                border: 2px solid {_ACCENT};
                border-radius: 10px;
            }}
            QLabel {{ color: #e0e0e0; background: transparent; }}
            QPushButton {{
                background: #292928; color: #e0e0e0;
                border: 1px solid #444; border-radius: 5px;
                padding: 5px 14px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #3a3a38; }}
            QPushButton#ok {{
                background: {_ACCENT}; color: #fff;
                font-weight: 700; border: none;
            }}
            QPushButton#ok:hover {{ background: #c93028; }}
            QPushButton#photo {{
                background: #292928; color: #e0e0e0;
                border: 1px solid #555; border-radius: 5px;
                padding: 5px 8px; font-size: 12px;
            }}
            QPushButton#photo:hover {{ background: #3a3a38; color: #fff; }}
            QPushButton#photo[captured="true"] {{
                background: #1a3320; color: #86efac;
                border-color: #22c55e;
            }}
            QSlider::groove:vertical {{
                background: #292928; width: 8px; border-radius: 4px; margin: 0 8px;
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
                background: #292928; border-radius: 4px; margin: 0 8px;
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
            lbl.setStyleSheet("font-size: 9px; color: #888;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tick_col.addWidget(lbl, stretch=1)
        slider_row.addLayout(tick_col)

        lbl_m = QLabel("m")
        lbl_m.setStyleSheet("font-size: 9px; color: #888;")
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
        hint.setStyleSheet("font-size: 8px; color: #888;")
        outer.addWidget(hint)

        # Photo capture preview (16:9, 192×108)
        self._photo_preview = QLabel("Pas de photo")
        self._photo_preview.setFixedSize(192, 108)
        self._photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_preview.setStyleSheet(
            "background: #292928; color: #888; border-radius: 4px; font-size: 10px;"
        )
        outer.addWidget(self._photo_preview)

        self._photo_btn = QPushButton("📷 Capturer photo")
        self._photo_btn.setObjectName("photo")
        self._photo_btn.clicked.connect(self._capture_photo)
        outer.addWidget(self._photo_btn)

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

    def _capture_photo(self) -> None:
        captured: list[QPixmap | None] = [None]

        def _on_snap(pix: QPixmap) -> None:
            captured[0] = pix

        EventBus().publish_sync("camera.snapshot_request", _on_snap)

        pix = captured[0]
        if pix is None or pix.isNull():
            self._photo_preview.setText("Aucune caméra")
            return

        # Scale down for display
        preview = pix.scaled(
            192, 108,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._photo_preview.setPixmap(preview)

        # Convert full-size (max 640px) snapshot to JPEG bytes
        if pix.width() > 640:
            pix = pix.scaledToWidth(640, Qt.TransformationMode.SmoothTransformation)
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        pix.save(tmp.name, "JPEG", 82)
        with open(tmp.name, "rb") as f:
            jpeg_bytes = f.read()
        os.unlink(tmp.name)
        self._photo_data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()

        self._photo_btn.setText("✓ Photo capturée")
        self._photo_btn.setProperty("captured", "true")
        self._photo_btn.style().polish(self._photo_btn)

        # Send to OCR endpoint asynchronously
        self._post_ocr(jpeg_bytes)

    def _post_ocr(self, jpeg_bytes: bytes) -> None:
        if not self._ocr_url:
            return
        if self._nam_ocr is None:
            self._nam_ocr = QNetworkAccessManager(self)

        part = QHttpPart()
        part.setHeader(
            QNetworkRequest.KnownHeaders.ContentDispositionHeader,
            'form-data; name="image"; filename="snapshot.jpg"',
        )
        part.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "image/jpeg")
        part.setBody(jpeg_bytes)

        multipart = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType, self)
        multipart.append(part)

        request = QNetworkRequest(QUrl(self._ocr_url))
        reply = self._nam_ocr.post(request, multipart)
        multipart.setParent(reply)
        reply.finished.connect(lambda r=reply: self._on_ocr_reply(r))

    def _on_ocr_reply(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._event_bus.publish_sync(
                    "log", f"[OCR] Erreur réseau: {reply.errorString()}"
                )
                return
            import json as _json
            data = _json.loads(bytes(reply.readAll()))
            text = str(data.get("text", "")).strip()
            ms   = data.get("processing_time_ms", "?")
            if text:
                self._event_bus.publish_sync("log", f"[OCR] Titre POI: «{text}» ({ms} ms)")
            else:
                self._event_bus.publish_sync("log", f"[OCR] Aucun texte détecté ({ms} ms)")
        finally:
            reply.deleteLater()

    def altitude(self) -> float:
        return self._altitude

    def photo_data_url(self) -> str | None:
        return self._photo_data_url


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

        # Custom image cache (loaded once on first use)
        self._robot_cursor_pixmap: QPixmap | None = None
        self._poi_pixmap: QPixmap | None = None
        self._robot_img_tried: bool = False
        self._poi_img_tried: bool = False

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
        ocr_url = str(self.config.get("ocr_url", "http://localhost:8080/camera/ocr")).strip()
        picker = _AltitudePicker(self.event_bus, ocr_url, self._widget)

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
        photo_url = picker.photo_data_url()

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
            label   = f"#{self._poi_seq}"
            poi_id  = f"poi_{self._poi_seq}"

            poi_payload: dict = {
                "lat":    poi_lat,
                "lng":    poi_lng,
                "label":  label,
                "alt":    altitude,
                "poi_id": poi_id,
            }
            if photo_url:
                poi_payload["photo"] = photo_url

            self.event_bus.publish_sync(poi_topic, poi_payload)

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

    def _load_image(self, config_key: str, tried_flag: str, cache_attr: str) -> QPixmap | None:
        if getattr(self, tried_flag):
            return getattr(self, cache_attr)
        setattr(self, tried_flag, True)
        img_path = str(self.config.get(config_key, "")).strip()
        if not img_path:
            return None
        p = Path(img_path) if Path(img_path).is_absolute() else Path(__file__).resolve().parents[3] / img_path
        pix = QPixmap(str(p))
        result = pix if not pix.isNull() else None
        setattr(self, cache_attr, result)
        return result

    def _draw_robot_cursor(
        self, painter: QPainter, cx: int, cy: int, yaw_deg: float, size: int
    ) -> None:
        """Arrow centred at (cx, cy) pointing in the heading direction."""
        pix = self._load_image("robot_cursor_image", "_robot_img_tried", "_robot_cursor_pixmap")
        if pix is not None:
            dim = size * 2
            scaled = pix.scaled(
                dim, dim,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(yaw_deg)
            painter.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
            painter.restore()
            return

        # Fallback: SVG-style arrow
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(yaw_deg)

        ring_r = int(size * 1.15)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawEllipse(-ring_r, -ring_r, ring_r * 2, ring_r * 2)

        tip_y   = -int(size * 0.85)
        base_y  =  int(size * 0.55)
        base_hw =  int(size * 0.45)
        arrow = QPolygonF([
            QPointF(0,        tip_y),
            QPointF(-base_hw, base_y),
            QPointF(base_hw,  base_y),
        ])
        painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
        painter.setBrush(QColor(34, 197, 94, 230))
        painter.drawPolygon(arrow)

        dot_r = max(3, size // 7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(239, 68, 68, 240))
        painter.drawEllipse(-dot_r, -dot_r, dot_r * 2, dot_r * 2)

        painter.restore()

    def _draw_pois(self, painter: QPainter, w: int, h: int) -> None:
        r = max(7, min(w, h) // 40)
        font_size = max(7, min(w, h) // 55)
        painter.setFont(QFont("Sans Serif", font_size, QFont.Weight.Bold))
        poi_pix = self._load_image("poi_image", "_poi_img_tried", "_poi_pixmap")

        for poi in self._pois:
            px = int(poi["nx"] * w)
            py = int(poi["ny"] * h)

            if poi_pix is not None:
                # Custom image — anchored at bottom-centre
                ih = r * 3
                iw = int(ih * poi_pix.width() / max(1, poi_pix.height()))
                scaled = poi_pix.scaled(
                    iw, ih,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter.drawPixmap(px - scaled.width() // 2, py - scaled.height(), scaled)
            else:
                # Fallback: golden pin
                painter.setPen(QPen(QColor("#78350f"), 2))
                painter.setBrush(QColor(245, 158, 11, 220))
                painter.drawEllipse(px - r, py - r, r * 2, r * 2)

                stem = max(3, r // 2)
                painter.setPen(QPen(QColor("#f59e0b"), max(2, stem // 2)))
                painter.drawLine(px, py + r, px, py + r + stem)

                cr = max(2, r // 3)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 230))
                painter.drawEllipse(px - cr, py - cr, cr * 2, cr * 2)

            # Label + altitude (shadow then white) — always drawn
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
