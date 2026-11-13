from __future__ import annotations

import base64
import math
import random
import tempfile
import os
from pathlib import Path

from PySide6.QtCore import QDateTime, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF, QRegion
from PySide6.QtNetwork import (
    QHttpMultiPart, QHttpPart,
    QNetworkAccessManager, QNetworkReply, QNetworkRequest,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from src.controller.event_bus import EventBus
from src.views.theme import (
    BG_DEEP, BG_DARK, BG_PANEL, BG_SURFACE,
    BORDER_DIM, BORDER, BORDER_BRIGHT,
    CYAN, GREEN, RED, TEXT, TEXT_DIM,
)


# ── Shared dialog styling ─────────────────────────────────────────────────────

_DIALOG_BASE = f"""
QDialog {{
    background: {BG_DEEP};
    border: 1px solid {CYAN};
}}
QLabel {{
    color: {TEXT};
    background: transparent;
    font-family: 'Courier New', monospace;
}}
QPushButton {{
    background: {BG_DARK};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 0;
    padding: 10px 16px;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    letter-spacing: 1.5px;
    min-height: 44px;
}}
QPushButton:hover {{
    background: {BG_SURFACE};
    border-color: {CYAN};
    color: {CYAN};
}}
QPushButton:pressed {{ background: {BG_DEEP}; }}
QPushButton#ok {{
    background: {CYAN};
    color: {BG_DEEP};
    border: none;
    font-weight: 700;
    letter-spacing: 2px;
}}
QPushButton#ok:hover {{ background: #ffc840; color: {BG_DEEP}; }}
QPushButton#cancel:hover {{ border-color: {RED}; color: {RED}; }}
QSlider::groove:horizontal {{
    background: {BG_SURFACE};
    height: 4px;
    border: none;
    margin: 14px 0;
}}
QSlider::handle:horizontal {{
    background: {CYAN};
    width: 36px; height: 36px;
    margin: -16px 0;
    border-radius: 0;
    border: 2px solid {BG_DEEP};
}}
QSlider::sub-page:horizontal {{
    background: {CYAN};
    margin: 14px 0;
}}
QSlider::add-page:horizontal {{
    background: {BG_DARK};
    margin: 14px 0;
}}
QPushButton[role="step"] {{
    background: {BG_SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 0;
    font-size: 13px;
    font-weight: 700;
    min-height: 54px;
    padding: 0 10px;
}}
QPushButton[role="step"]:hover {{
    background: {BG_PANEL};
    border-color: {CYAN};
    color: {CYAN};
}}
QPushButton[role="step"]:pressed {{ background: {BG_DEEP}; }}
QPushButton[role="preset"] {{
    background: {BG_SURFACE};
    color: {TEXT_DIM};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    font-size: 10px;
    font-weight: 700;
    min-height: 42px;
    padding: 0;
    letter-spacing: 1px;
}}
QPushButton[role="preset"]:hover {{
    background: {BG_PANEL};
    border-color: {CYAN};
    color: {CYAN};
}}
QPushButton[role="preset"]:pressed {{ background: {BG_DEEP}; }}
QPushButton#photo {{
    background: {BG_DARK};
    color: {TEXT_DIM};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    padding: 6px 10px;
    font-size: 11px;
    letter-spacing: 1px;
}}
QPushButton#photo:hover {{ border-color: {CYAN}; color: {TEXT}; }}
QPushButton#photo[captured="true"] {{
    background: rgba(0,230,118,0.05);
    color: {GREEN};
    border-color: {GREEN};
}}
QPushButton[role="key"] {{
    background: {BG_DARK};
    color: {TEXT};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    padding: 0;
    font-family: 'Courier New', monospace;
    font-size: 15px;
    font-weight: 600;
}}
QPushButton[role="key"]:hover {{
    background: {BG_SURFACE};
    border-color: {CYAN};
    color: {CYAN};
}}
QPushButton[role="key"]:pressed {{ background: {BG_DEEP}; }}
QPushButton#bs {{
    background: rgba(255,61,61,0.06);
    color: {RED};
    border: 1px solid rgba(255,61,61,0.25);
    border-radius: 0;
    padding: 0;
    font-size: 18px;
}}
QPushButton#bs:hover {{ background: rgba(255,61,61,0.13); border-color: {RED}; }}
QPushButton#space {{
    background: {BG_DARK};
    color: {TEXT_DIM};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    letter-spacing: 2px;
    font-size: 10px;
    padding: 0;
}}
QPushButton#space:hover {{
    background: {BG_SURFACE};
    border-color: {BORDER_BRIGHT};
    color: {TEXT};
}}
"""


def _tac_titlebar(text: str) -> QWidget:
    """Returns a 30px title-bar widget with orange label, used at dialog top."""
    bar = QWidget()
    bar.setFixedHeight(30)
    bar.setStyleSheet(
        f"background: {BG_PANEL}; border-bottom: 1px solid {BORDER};"
    )
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(10, 0, 8, 0)
    lay.setSpacing(7)
    icon = QLabel("◈")
    icon.setStyleSheet(f"color: {CYAN}; font-size: 11px;")
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {CYAN}; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
    )
    lay.addWidget(icon)
    lay.addWidget(lbl)
    lay.addStretch()
    return bar


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
        self.setFixedWidth(360)
        self._altitude = 0.0
        self._photo_data_url: str | None = None
        self._nam_ocr: QNetworkAccessManager | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet(_DIALOG_BASE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_tac_titlebar("ALTITUDE — P.O.I."))

        body = QWidget()
        inner = QVBoxLayout(body)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(10)
        outer.addWidget(body)

        # Value readout
        self._val_label = QLabel("0.00 m")
        self._val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_label.setStyleSheet(
            f"font-size: 42px; font-weight: 700; letter-spacing: 2px;"
            f" color: {CYAN}; padding: 8px 0;"
            f" background: {BG_DARK}; border: 1px solid {BORDER_DIM};"
        )
        inner.addWidget(self._val_label)

        # Step buttons row  (-0.5 | -0.1 | +0.1 | +0.5)
        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        for delta, lbl_txt in [(-0.5, "−0.5"), (-0.1, "−0.1"), (+0.1, "+0.1"), (+0.5, "+0.5")]:
            btn = QPushButton(lbl_txt)
            btn.setProperty("role", "step")
            btn.clicked.connect(lambda _=False, d=delta: self._adjust(d))
            step_row.addWidget(btn)
        inner.addLayout(step_row)

        # Horizontal slider (fine adjustment)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 500)
        self._slider.setValue(0)
        self._slider.setFixedHeight(56)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(10)
        self._slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._slider.valueChanged.connect(self._on_slider)
        inner.addWidget(self._slider)

        # Quick preset row
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for val in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
            pb = QPushButton(f"{val:.1f}m")
            pb.setProperty("role", "preset")
            pb.clicked.connect(lambda _=False, v=val: self._set_alt(v))
            preset_row.addWidget(pb)
        inner.addLayout(preset_row)

        # Divider
        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {BORDER_DIM};")
        inner.addWidget(div)

        # Photo preview
        self._photo_preview = QLabel("AUCUNE PHOTO")
        self._photo_preview.setFixedSize(214, 120)
        self._photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_preview.setStyleSheet(
            f"background: {BG_DARK}; color: {TEXT_DIM};"
            f" border: 1px solid {BORDER_DIM}; font-size: 9px; letter-spacing: 1.5px;"
        )
        inner.addWidget(self._photo_preview)

        self._photo_btn = QPushButton("📷  CAPTURER PHOTO")
        self._photo_btn.setObjectName("photo")
        self._photo_btn.clicked.connect(self._capture_photo)
        inner.addWidget(self._photo_btn)

        # Divider
        div2 = QWidget(); div2.setFixedHeight(1)
        div2.setStyleSheet(f"background: {BORDER_DIM};")
        inner.addWidget(div2)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("ANNULER")
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("◆  CONFIRMER")
        ok_btn.setObjectName("ok")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            f"QPushButton {{ background: {CYAN}; color: #000000; border: none;"
            f" font-weight: 700; letter-spacing: 2px; padding: 7px 16px;"
            f" font-family: 'Courier New', monospace; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #ffc840; color: #000000; }}"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        inner.addLayout(btn_row)

    def _on_slider(self, value: int) -> None:
        self._altitude = value / 100.0
        self._val_label.setText(f"{self._altitude:.2f} m")

    def _adjust(self, delta: float) -> None:
        self._set_alt(self._altitude + delta)

    def _set_alt(self, value: float) -> None:
        value = max(0.0, min(5.0, round(value, 2)))
        self._altitude = value
        self._slider.blockSignals(True)
        self._slider.setValue(int(value * 100))
        self._slider.blockSignals(False)
        self._val_label.setText(f"{value:.2f} m")

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


# ── Orbit radius picker dialog ────────────────────────────────────────────────

class _RadiusPicker(QDialog):
    """Modal popup to pick orbit radius (1–200 m)."""

    def __init__(self, default_radius: float = 10.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orbit — Rayon")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setFixedWidth(360)
        self._radius = float(max(1.0, min(200.0, default_radius)))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_DIALOG_BASE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_tac_titlebar("ORBIT — RAYON"))

        body = QWidget()
        inner = QVBoxLayout(body)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(10)
        outer.addWidget(body)

        self._val_label = QLabel(f"{self._radius:.0f} m")
        self._val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_label.setStyleSheet(
            f"font-size: 42px; font-weight: 700; letter-spacing: 2px;"
            f" color: {CYAN}; padding: 8px 0;"
            f" background: {BG_DARK}; border: 1px solid {BORDER_DIM};"
        )
        inner.addWidget(self._val_label)

        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        for delta, lbl_txt in [(-10, "−10"), (-1, "−1"), (+1, "+1"), (+10, "+10")]:
            btn = QPushButton(lbl_txt)
            btn.setProperty("role", "step")
            btn.clicked.connect(lambda _=False, d=delta: self._adjust(d))
            step_row.addWidget(btn)
        inner.addLayout(step_row)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(1, 200)
        self._slider.setValue(int(self._radius))
        self._slider.setFixedHeight(56)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(10)
        self._slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._slider.valueChanged.connect(self._on_slider)
        inner.addWidget(self._slider)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for val in (5, 10, 20, 50, 100, 150):
            pb = QPushButton(f"{val}m")
            pb.setProperty("role", "preset")
            pb.clicked.connect(lambda _=False, v=val: self._set_radius(v))
            preset_row.addWidget(pb)
        inner.addLayout(preset_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("ANNULER")
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("◆  CONFIRMER")
        ok_btn.setObjectName("ok")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        inner.addLayout(btn_row)

    def _on_slider(self, value: int) -> None:
        self._radius = float(value)
        self._val_label.setText(f"{value} m")

    def _adjust(self, delta: float) -> None:
        self._set_radius(self._radius + delta)

    def _set_radius(self, value: float) -> None:
        value = float(max(1.0, min(200.0, round(value))))
        self._radius = value
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        self._val_label.setText(f"{value:.0f} m")

    def radius(self) -> float:
        return self._radius


# ── Virtual keyboard dialog ───────────────────────────────────────────────────

class _NamePicker(QDialog):
    """On-screen QWERTY keyboard for naming a POI."""

    _KB_ROWS = [
        "1234567890",
        "QWERTYUIOP",
        "ASDFGHJKL",
        "ZXCVBNM",
    ]
    _KEY_W = 44
    _KEY_H = 52
    _KEY_GAP = 6

    def __init__(self, default_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self._text = default_name
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet(_DIALOG_BASE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_tac_titlebar("IDENTIFIANT — P.O.I."))

        body = QWidget()
        inner = QVBoxLayout(body)
        inner.setContentsMargins(12, 12, 12, 14)
        inner.setSpacing(8)
        outer.addWidget(body)

        self._display = QLabel()
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setStyleSheet(
            f"font-size: 20px; font-weight: 700;"
            f" background: {BG_DARK}; border: 1px solid {BORDER};"
            f" padding: 6px 10px; min-height: 36px; color: {CYAN};"
            f" font-family: 'Courier New', monospace;"
        )
        self._display.setMinimumWidth(460)
        inner.addWidget(self._display)
        self._refresh_display()

        for row_str in self._KB_ROWS:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(self._KEY_GAP)
            row_layout.addStretch()
            for ch in row_str:
                btn = QPushButton(ch)
                btn.setProperty("role", "key")
                btn.setFixedSize(self._KEY_W, self._KEY_H)
                btn.clicked.connect(lambda _=False, c=ch: self._press(c))
                row_layout.addWidget(btn)
            row_layout.addStretch()
            inner.addLayout(row_layout)

        # Space + backspace row
        bot = QHBoxLayout()
        bot.setSpacing(self._KEY_GAP)
        space_btn = QPushButton("ESPACE")
        space_btn.setObjectName("space")
        space_btn.setFixedHeight(self._KEY_H)
        space_btn.clicked.connect(lambda: self._press(" "))
        bs_btn = QPushButton("⌫")
        bs_btn.setObjectName("bs")
        bs_btn.setFixedSize(self._KEY_W * 2 + self._KEY_GAP, self._KEY_H)
        bs_btn.clicked.connect(self._backspace)
        bot.addWidget(space_btn, 1)
        bot.addWidget(bs_btn)
        inner.addLayout(bot)

        # Divider
        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {BORDER_DIM};")
        inner.addWidget(div)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("ANNULER")
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("◆  CONFIRMER")
        ok_btn.setObjectName("ok")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            f"QPushButton {{ background: {CYAN}; color: #000000; border: none;"
            f" font-weight: 700; letter-spacing: 2px; padding: 7px 16px;"
            f" font-family: 'Courier New', monospace; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #ffc840; color: #000000; }}"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        inner.addLayout(btn_row)

    def _press(self, char: str) -> None:
        self._text += char
        self._refresh_display()

    def _backspace(self) -> None:
        self._text = self._text[:-1]
        self._refresh_display()

    def _refresh_display(self) -> None:
        self._display.setText((self._text + "▌") if self._text else "▌")

    def name(self) -> str:
        return self._text


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

class _CircularWidget(QWidget):
    """QWidget clipped to a circle with a cyan border ring."""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        s = min(self.width(), self.height())
        x = (self.width()  - s) // 2
        y = (self.height() - s) // 2
        self.setMask(QRegion(x, y, s, s, QRegion.RegionType.Ellipse))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(self.width(), self.height())
        x = (self.width()  - s) // 2
        y = (self.height() - s) // 2
        p.setPen(QPen(QColor(CYAN), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(x + 1, y + 1, s - 2, s - 2)


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

        if self.config.get("round"):
            self._widget = _CircularWidget()
            self._widget.setMinimumSize(160, 160)
        else:
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
        self._register_gps_poi_sync()
        self._register_matrix_feed()

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

    # ── GPS POI sync (map → costmap) ──────────────────────────────────────────

    def _register_gps_poi_sync(self) -> None:
        """Subscribe to GPS POI events and project them onto the bitmap."""
        topic = str(self.config.get("add_poi_gps_topic", "")).strip()
        if not topic:
            return

        radius_x = float(self.config.get("cornerPositionWidth",  1.0)) / 2.0
        radius_y = float(self.config.get("cornerPositionHeight", 1.0)) / 2.0

        def _on_gps_poi(payload) -> None:
            if not isinstance(payload, dict):
                return
            if self._robot_lat is None or self._robot_lng is None:
                return
            try:
                poi_lat = float(payload["lat"])
                poi_lng = float(payload["lng"])
            except (KeyError, TypeError, ValueError):
                return

            label = str(payload.get("label", "POI"))
            alt   = float(payload.get("alt", 0.0))

            # GPS offset → metres (north/east)
            north = (poi_lat - self._robot_lat) * 111_111.0
            east  = (poi_lng - self._robot_lng) * (
                111_111.0 * math.cos(math.radians(self._robot_lat))
            )

            # Rotate into robot-local frame (inverse of forward rotation)
            yaw_rad = math.radians(self._robot_yaw)
            lx =  east * math.cos(yaw_rad) + north * math.sin(yaw_rad)
            ly = -east * math.sin(yaw_rad) + north * math.cos(yaw_rad)

            # Local → normalised image coordinates
            nx = 0.5 + lx / (2.0 * radius_x)
            ny = 0.5 - ly / (2.0 * radius_y)   # y axis inverted in image

            if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
                return  # POI is outside the visible bitmap area

            self._pois.append({"nx": nx, "ny": ny, "alt": alt, "label": label})
            self._update_display()

        self.event_bus.subscribe(topic, _on_gps_poi)

    # ── Matrix costmap feed ────────────────────────────────────────────────────

    def _register_matrix_feed(self) -> None:
        topic = str(self.config.get("data_topic", "")).strip()
        if not topic:
            return
        def _on_matrix(mat) -> None:
            pix = self._render_matrix(mat)
            if pix is not None:
                self._raw_pixmap = pix
                self._update_display()
        self.event_bus.subscribe(topic, _on_matrix)
        self._raw_pixmap = self._make_placeholder_pixmap(200, 200)
        self._update_display()

    @staticmethod
    def _render_matrix(matrix) -> "QPixmap | None":
        from PySide6.QtGui import QImage
        try:
            import numpy as np
            arr = np.asarray(matrix, dtype=np.float32)
            if arr.ndim != 2:
                return None
            h, w = arr.shape

            rgba = np.zeros((h, w, 4), dtype=np.uint8)

            # -1  unknown → dark gray, semi-opaque
            u = arr < 0
            rgba[u] = (70, 70, 70, 180)

            # 0   free    → fully transparent
            f = arr == 0
            rgba[f] = (0, 0, 0, 0)

            # 1-99 cost   → green→yellow→red heatmap
            c = (arr > 0) & (arr < 100)
            t = (arr[c] / 99.0).clip(0.0, 1.0)
            rgba[c, 0] = (t * 255).astype(np.uint8)
            rgba[c, 1] = ((1.0 - t) * 220).astype(np.uint8)
            rgba[c, 2] = np.zeros(t.shape, np.uint8)
            rgba[c, 3] = (120 + t * 135).astype(np.uint8)

            # 100 lethal  → bright red, fully opaque
            lo = arr >= 100
            rgba[lo] = (255, 40, 40, 255)

            img = QImage(rgba.tobytes(), w, h, w * 4, QImage.Format.Format_RGBA8888)
            return QPixmap.fromImage(img)

        except ImportError:
            pass

        # ── Pure-Python fallback (no numpy) ──────────────────────────────
        try:
            rows = list(matrix)
            h = len(rows)
            if h == 0:
                return None
            w = len(rows[0])
            buf = bytearray(w * h * 4)
            for y, row in enumerate(rows):
                base = y * w * 4
                for x, val in enumerate(row):
                    i = base + x * 4
                    if val < 0:
                        buf[i:i+4] = (70, 70, 70, 180)
                    elif val == 0:
                        buf[i:i+4] = (0, 0, 0, 0)
                    elif val < 100:
                        t = val / 99.0
                        buf[i]   = int(t * 255)
                        buf[i+1] = int((1.0 - t) * 220)
                        buf[i+2] = 0
                        buf[i+3] = int(120 + t * 135)
                    else:
                        buf[i:i+4] = (255, 40, 40, 255)
            img = QImage(bytes(buf), w, h, w * 4, QImage.Format.Format_RGBA8888)
            return QPixmap.fromImage(img)
        except Exception:
            return None

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

        altitude  = picker.altitude()
        photo_url = picker.photo_data_url()

        # Virtual keyboard — name the POI before creating it
        next_seq     = self._poi_seq + 1
        default_name = f"#{next_seq}"
        name_picker  = _NamePicker(default_name, self._widget)
        if self._widget:
            center = self._widget.mapToGlobal(self._widget.rect().center())
            name_picker.adjustSize()
            name_picker.move(
                center.x() - name_picker.width()  // 2,
                center.y() - name_picker.height() // 2,
            )
        if name_picker.exec() != QDialog.DialogCode.Accepted:
            return

        self._poi_seq = next_seq
        label  = name_picker.name() or default_name
        poi_id = f"poi_{self._poi_seq}"

        radius_x = float(self.config.get("cornerPositionWidth",  1.0)) / 2.0
        radius_y = float(self.config.get("cornerPositionHeight", 1.0)) / 2.0
        local_x = (nx - 0.5) * 2.0 * radius_x
        local_y = (0.5 - ny) * 2.0 * radius_y

        payload: dict = {
            "x":    round(local_x, 3),
            "y":    round(local_y, 3),
            "z":    round(altitude, 2),
            "tilt": round(self._robot_yaw, 2),
        }

        poi_topic = str(self.config.get("poi_topic", "")).strip()
        if poi_topic:
            has_gps   = self._robot_lat is not None and self._robot_lng is not None
            robot_lat = self._robot_lat if has_gps else 0.0
            robot_lng = self._robot_lng if has_gps else 0.0

            yaw_rad = math.radians(self._robot_yaw)
            east    = local_x * math.cos(yaw_rad) - local_y * math.sin(yaw_rad)
            north   = local_x * math.sin(yaw_rad) + local_y * math.cos(yaw_rad)

            ref_lat = robot_lat if has_gps else 45.5017
            poi_lat = robot_lat + north / 111_111.0
            poi_lng = robot_lng + east  / (111_111.0 * math.cos(math.radians(ref_lat)))

            payload["lat"] = round(poi_lat, 8)
            payload["lng"] = round(poi_lng, 8)

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

            self._pois.append({"nx": nx, "ny": ny, "alt": altitude, "label": label})
            self._update_display()

        click_topic = str(self.config.get("click_topic", "costmap.click")).strip()
        self.event_bus.publish_sync(click_topic, payload)
        self.event_bus.publish_sync(
            "log",
            f"[Bitmap:{self.name}] POI {self._poi_seq} «{label}» → "
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
        painter.setPen(QPen(QColor(0xff, 0xae, 0x00, 80), 1))
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawEllipse(-ring_r, -ring_r, ring_r * 2, ring_r * 2)

        tip_y   = -int(size * 0.85)
        base_y  =  int(size * 0.55)
        base_hw =  int(size * 0.45)
        arrow = QPolygonF([
            QPointF(0,        tip_y),
            QPointF(-base_hw, base_y),
            QPointF(base_hw,  base_y),
        ])
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
        painter.setBrush(QColor(0xff, 0xae, 0x00, 230))
        painter.drawPolygon(arrow)

        dot_r = max(3, size // 7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0x08, 0x08, 0x08, 220))
        painter.drawEllipse(-dot_r, -dot_r, dot_r * 2, dot_r * 2)

        painter.restore()

    def _draw_pois(self, painter: QPainter, w: int, h: int) -> None:
        r = max(7, min(w, h) // 40)
        font_size = max(7, min(w, h) // 55)
        painter.setFont(QFont("Courier New", font_size, QFont.Weight.Bold))
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
                # Tactical diamond (losange)
                d = QPolygonF([
                    QPointF(px,     py - r),
                    QPointF(px + r, py),
                    QPointF(px,     py + r),
                    QPointF(px - r, py),
                ])
                painter.setPen(QPen(QColor(0x08, 0x08, 0x08, 200), 1))
                painter.setBrush(QColor(0xff, 0xae, 0x00, 210))
                painter.drawPolygon(d)
                # Inner highlight dot
                cr = max(2, r // 3)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xff, 0xff, 0xff, 140))
                painter.drawEllipse(px - cr, py - cr, cr * 2, cr * 2)

            # Label: dark shadow + orange text
            text = f"◆ {poi['label']}  {poi['alt']:.2f}m"
            tx, ty = px + r + 4, py + font_size // 2
            painter.setPen(QPen(QColor(0, 0, 0, 180), 1))
            painter.drawText(tx + 1, ty + 1, text)
            painter.setPen(QPen(QColor(0xff, 0xae, 0x00), 1))
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
