from __future__ import annotations

import math
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QProgressBar, QTextEdit, QComboBox, QFrame,
)

from src.views import theme
from src.controller.event_bus import EventBus

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "ELROB 2026 — Thun, CH": (7.57, 46.72, 7.68, 46.80),
}

_SOURCES: dict[str, str] = {
    "Satellite (ArcGIS)": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ),
    "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

_SAT_URL   = _SOURCES["Satellite (ArcGIS)"]
_LOCAL_TMPL = "http://localhost:{port}/tiles/{{z}}/{{x}}/{{y}}.png"

# ── Tile math ──────────────────────────────────────────────────────────────────

def _tile_range(lng_min: float, lat_min: float, lng_max: float, lat_max: float, z: int):
    n = 2 ** z
    def _xy(lat: float, lng: float):
        lr = math.radians(lat)
        x = int((lng + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(lr)) / math.pi) / 2 * n)
        return x, y
    x0, y0 = _xy(lat_max, lng_min)
    x1, y1 = _xy(lat_min, lng_max)
    return min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)


def _count_tiles(lng_min: float, lat_min: float, lng_max: float, lat_max: float,
                 z_min: int, z_max: int) -> int:
    total = 0
    for z in range(z_min, z_max + 1):
        x0, x1, y0, y1 = _tile_range(lng_min, lat_min, lng_max, lat_max, z)
        total += (x1 - x0 + 1) * (y1 - y0 + 1)
    return total


def _iter_tiles(lng_min: float, lat_min: float, lng_max: float, lat_max: float,
                z_min: int, z_max: int):
    for z in range(z_min, z_max + 1):
        x0, x1, y0, y1 = _tile_range(lng_min, lat_min, lng_max, lat_max, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield z, x, y


# ── Download worker ────────────────────────────────────────────────────────────

class _Worker(QThread):
    progress = Signal(int, int)
    logged   = Signal(str)
    finished = Signal(bool)

    def __init__(self, bbox: tuple, z_min: int, z_max: int,
                 url_tpl: str, out_dir: Path):
        super().__init__()
        self._bbox    = bbox
        self._z_min   = z_min
        self._z_max   = z_max
        self._url_tpl = url_tpl
        self._out     = out_dir
        self._stop    = False

    def cancel(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            import requests  # noqa: PLC0415
        except ImportError:
            self.logged.emit("ERROR: pip install requests")
            self.finished.emit(False)
            return

        tiles = list(_iter_tiles(*self._bbox, self._z_min, self._z_max))
        total = len(tiles)
        self.logged.emit(f"Starting: {total} tiles  (zoom {self._z_min}→{self._z_max})")

        sess = requests.Session()
        sess.headers["User-Agent"] = "Mozilla/5.0"
        done = 0

        for z, x, y in tiles:
            if self._stop:
                self.logged.emit("Cancelled.")
                self.finished.emit(False)
                return

            path = self._out / str(z) / str(x) / f"{y}.png"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    r = sess.get(self._url_tpl.format(z=z, x=x, y=y), timeout=10)
                    if r.status_code == 200:
                        path.write_bytes(r.content)
                    else:
                        self.logged.emit(f"  HTTP {r.status_code}: {z}/{x}/{y}")
                except Exception as exc:
                    self.logged.emit(f"  Error {z}/{x}/{y}: {exc}")

            done += 1
            self.progress.emit(done, total)
            if done % 250 == 0:
                self.logged.emit(f"  {done}/{total}  ({done * 100 // total}%)")
            time.sleep(0.03)

        self.logged.emit(f"Done — {total} tiles → {self._out}")
        self.finished.emit(True)


# ── In-process tile HTTP server ────────────────────────────────────────────────

class _TileHandler(SimpleHTTPRequestHandler):
    """Static file handler that adds CORS + cache headers and suppresses access logs."""

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "max-age=3600")
        super().end_headers()

    def log_message(self, *_args) -> None:
        pass


class _TileServer(threading.Thread):
    def __init__(self, root: Path, port: int):
        super().__init__(daemon=True)
        self._root = root
        self._port = port
        self._httpd: HTTPServer | None = None
        self.error: str = ""

    def run(self) -> None:
        try:
            handler = lambda *a, **kw: _TileHandler(*a, directory=str(self._root), **kw)
            self._httpd = HTTPServer(("", self._port), handler)
            self._httpd.serve_forever()
        except OSError as exc:
            self.error = str(exc)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None


# ── Shared style fragments ─────────────────────────────────────────────────────

def _btn_style(color: str = theme.CYAN) -> str:
    return f"""
        QPushButton {{
            background: {theme.BG_SURFACE};
            color: {theme.TEXT_DIM};
            border: 1px solid {theme.BORDER};
            font-family: {theme.FONT_MONO};
            font-size: 10px;
            letter-spacing: 1px;
            padding: 5px 12px;
        }}
        QPushButton:hover  {{ color: {color}; border-color: {color}; background: #252525; }}
        QPushButton:pressed {{ background: {theme.BG_DARK}; }}
        QPushButton:disabled {{ color: #333; border-color: {theme.BORDER_DIM}; }}
    """

def _spin_style() -> str:
    return f"""
        QDoubleSpinBox, QSpinBox {{
            background: {theme.BG_SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            font-family: {theme.FONT_MONO};
            font-size: 10px;
            padding: 3px 6px;
        }}
        QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {theme.CYAN}; }}
    """


# ── TileDownloader component ───────────────────────────────────────────────────

class TileDownloader:
    def __init__(self, name: str, config: dict, event_bus: EventBus | None = None):
        self.name        = name
        self.config      = config
        self._bus        = event_bus or EventBus()
        self._widget: QWidget | None = None
        self._worker: _Worker | None = None
        self._tile_server: _TileServer | None = None
        self._port       = int(config.get("server_port", 8181))
        self._tiles_dir  = _PROJECT_ROOT / str(config.get("tiles_dir", "tiles"))
        self._tile_topic = str(config.get("tile_source_topic", "")).strip()

        # UI refs
        self._preset_combo: QComboBox | None = None
        self._source_combo: QComboBox | None = None
        self._lng_min: QDoubleSpinBox | None = None
        self._lat_min: QDoubleSpinBox | None = None
        self._lng_max: QDoubleSpinBox | None = None
        self._lat_max: QDoubleSpinBox | None = None
        self._z_min:   QSpinBox | None = None
        self._z_max:   QSpinBox | None = None
        self._lbl_estimate: QLabel | None = None
        self._progress: QProgressBar | None = None
        self._log: QTextEdit | None = None
        self._btn_dl: QPushButton | None = None
        self._btn_cancel: QPushButton | None = None
        self._btn_server: QPushButton | None = None
        self._lbl_server: QLabel | None = None

    # ── Build ──────────────────────────────────────────────────────────────────

    def build(self) -> None:
        w = QWidget()
        w.setStyleSheet(
            f"QWidget {{ background: {theme.BG_DEEP}; color: {theme.TEXT}; "
            f"font-family: {theme.FONT_MONO}; }}"
        )
        root = QVBoxLayout(w)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        # Title
        t = QLabel("◆ TILE DOWNLOADER")
        t.setStyleSheet(f"color: {theme.CYAN}; font-size: 12px; letter-spacing: 2px;")
        root.addWidget(t)

        # ── Row 1 : Preset + Source ──
        r1 = QHBoxLayout(); r1.setSpacing(10)
        r1.addWidget(self._dim("PRESET"))
        self._preset_combo = QComboBox()
        for n in _PRESETS: self._preset_combo.addItem(n)
        self._preset_combo.currentTextChanged.connect(self._on_preset)
        r1.addWidget(self._preset_combo)
        r1.addSpacing(24)
        r1.addWidget(self._dim("SOURCE"))
        self._source_combo = QComboBox()
        for n in _SOURCES: self._source_combo.addItem(n)
        r1.addWidget(self._source_combo)
        r1.addStretch()
        root.addLayout(r1)

        # ── Row 2 : BBox + Zoom ──
        r2 = QHBoxLayout(); r2.setSpacing(8)
        ss = _spin_style()
        for label, attr, default, lo, hi, dec in [
            ("LNG min", "_lng_min",  7.57, -180.0, 180.0, 5),
            ("LNG max", "_lng_max",  7.68, -180.0, 180.0, 5),
            ("LAT min", "_lat_min", 46.72,  -90.0,  90.0, 5),
            ("LAT max", "_lat_max", 46.80,  -90.0,  90.0, 5),
        ]:
            r2.addWidget(self._dim(label))
            sb = QDoubleSpinBox()
            sb.setStyleSheet(ss); sb.setRange(lo, hi)
            sb.setDecimals(dec); sb.setSingleStep(0.001); sb.setValue(default)
            sb.valueChanged.connect(self._update_estimate)
            setattr(self, attr, sb); r2.addWidget(sb)

        r2.addSpacing(20)
        r2.addWidget(self._dim("ZOOM"))
        self._z_min = QSpinBox()
        self._z_min.setStyleSheet(ss); self._z_min.setRange(0, 22)
        self._z_min.setValue(13); self._z_min.setFixedWidth(54)
        self._z_min.valueChanged.connect(self._update_estimate)
        r2.addWidget(self._z_min)
        r2.addWidget(self._dim("→"))
        self._z_max = QSpinBox()
        self._z_max.setStyleSheet(ss); self._z_max.setRange(0, 22)
        self._z_max.setValue(18); self._z_max.setFixedWidth(54)
        self._z_max.valueChanged.connect(self._update_estimate)
        r2.addWidget(self._z_max)
        r2.addStretch()
        root.addLayout(r2)

        # ── Estimate ──
        self._lbl_estimate = QLabel("…")
        self._lbl_estimate.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        root.addWidget(self._lbl_estimate)

        # ── Download buttons ──
        r3 = QHBoxLayout(); r3.setSpacing(8)
        self._btn_dl = QPushButton("▶  DOWNLOAD")
        self._btn_dl.setStyleSheet(_btn_style(theme.GREEN))
        self._btn_dl.clicked.connect(self._start_download)
        self._btn_cancel = QPushButton("✕  CANCEL")
        self._btn_cancel.setStyleSheet(_btn_style(theme.RED))
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._cancel_download)
        r3.addWidget(self._btn_dl); r3.addWidget(self._btn_cancel); r3.addStretch()
        root.addLayout(r3)

        # ── Progress bar ──
        self._progress = QProgressBar()
        self._progress.setRange(0, 100); self._progress.setValue(0)
        self._progress.setFixedHeight(12); self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{ background: {theme.BG_SURFACE}; border: 1px solid {theme.BORDER_DIM}; }}
            QProgressBar::chunk {{ background: {theme.GREEN}; }}
        """)
        root.addWidget(self._progress)

        # ── Log ──
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(100)
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background: {theme.BG_PANEL}; color: {theme.TEXT_DIM};
                border: 1px solid {theme.BORDER_DIM};
                font-family: {theme.FONT_MONO}; font-size: 10px;
            }}
        """)
        root.addWidget(self._log)

        # ── Separator ──
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep)

        # ── Tile server section ──
        srv_title = QLabel("◆ TILE SERVER")
        srv_title.setStyleSheet(f"color: {theme.CYAN}; font-size: 11px; letter-spacing: 2px;")
        root.addWidget(srv_title)

        r4 = QHBoxLayout(); r4.setSpacing(10)
        self._btn_server = QPushButton(f"▶  START  (:{self._port})")
        self._btn_server.setStyleSheet(_btn_style())
        self._btn_server.clicked.connect(self._toggle_server)
        self._lbl_server = QLabel("● STOPPED")
        self._lbl_server.setStyleSheet(f"color: {theme.RED}; font-size: 10px;")
        r4.addWidget(self._btn_server); r4.addWidget(self._lbl_server); r4.addStretch()
        root.addLayout(r4)

        # ── Map source switch (only if topic configured) ──
        if self._tile_topic:
            r5 = QHBoxLayout(); r5.setSpacing(8)
            btn_local = QPushButton("⇐  MAP → LOCAL TILES")
            btn_local.setStyleSheet(_btn_style(theme.CYAN))
            btn_local.clicked.connect(self._switch_to_local)
            btn_sat = QPushButton("⇒  MAP → SATELLITE")
            btn_sat.setStyleSheet(_btn_style(theme.TEXT_DIM))
            btn_sat.clicked.connect(self._switch_to_satellite)
            r5.addWidget(btn_local); r5.addWidget(btn_sat); r5.addStretch()
            root.addLayout(r5)

        root.addStretch()
        self._widget = w
        self._update_estimate()

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _dim(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 9px; letter-spacing: 1px;")
        return l

    def _bbox(self) -> tuple:
        return (
            self._lng_min.value(), self._lat_min.value(),
            self._lng_max.value(), self._lat_max.value(),
        )

    def _on_preset(self, name: str) -> None:
        coords = _PRESETS.get(name)
        if coords is None:
            return
        lng_min, lat_min, lng_max, lat_max = coords
        for sb, val in [(self._lng_min, lng_min), (self._lat_min, lat_min),
                        (self._lng_max, lng_max), (self._lat_max, lat_max)]:
            if sb:
                sb.blockSignals(True); sb.setValue(val); sb.blockSignals(False)
        self._update_estimate()

    def _update_estimate(self) -> None:
        if None in (self._lng_min, self._lat_min, self._lng_max, self._lat_max,
                    self._z_min, self._z_max, self._lbl_estimate):
            return
        n  = _count_tiles(*self._bbox(), self._z_min.value(), self._z_max.value())
        mb = n * 250 / 1024 / 1024
        self._lbl_estimate.setText(f"~{n:,} tiles  ·  ~{mb:.0f} Mo estimated")

    def _log_line(self, text: str) -> None:
        if self._log:
            self._log.append(text)

    # ── Download ───────────────────────────────────────────────────────────────

    def _start_download(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        src = self._source_combo.currentText() if self._source_combo else "Satellite (ArcGIS)"
        self._worker = _Worker(
            self._bbox(),
            self._z_min.value(), self._z_max.value(),
            _SOURCES.get(src, _SAT_URL),
            self._tiles_dir,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.logged.connect(self._log_line)
        self._worker.finished.connect(self._on_done)
        self._worker.start()
        if self._btn_dl:     self._btn_dl.setEnabled(False)
        if self._btn_cancel: self._btn_cancel.setEnabled(True)

    def _cancel_download(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int) -> None:
        if self._progress:
            self._progress.setValue(int(done * 100 / total) if total else 0)

    def _on_done(self, success: bool) -> None:
        if self._btn_dl:     self._btn_dl.setEnabled(True)
        if self._btn_cancel: self._btn_cancel.setEnabled(False)
        if self._progress:   self._progress.setValue(100 if success else 0)

    # ── Tile server ────────────────────────────────────────────────────────────

    def _toggle_server(self) -> None:
        if self._tile_server and self._tile_server.is_alive():
            self._tile_server.stop()
            self._tile_server = None
            if self._btn_server:
                self._btn_server.setText(f"▶  START  (:{self._port})")
            if self._lbl_server:
                self._lbl_server.setText("● STOPPED")
                self._lbl_server.setStyleSheet(f"color: {theme.RED}; font-size: 10px;")
        else:
            srv = _TileServer(_PROJECT_ROOT, self._port)
            srv.start()
            # Give the server 200 ms to bind or fail
            srv.join(0.2)
            if srv.error:
                self._log_line(f"Server error: {srv.error}  (port {self._port} already in use?)")
                return
            self._tile_server = srv
            if self._btn_server:
                self._btn_server.setText(f"■  STOP   (:{self._port})")
            if self._lbl_server:
                self._lbl_server.setText(f"● RUNNING :{self._port}")
                self._lbl_server.setStyleSheet(f"color: {theme.GREEN}; font-size: 10px;")
            self._log_line(f"Tile server started  :{self._port}  →  {_PROJECT_ROOT}")

    # ── Map source switch ──────────────────────────────────────────────────────

    def _switch_to_local(self) -> None:
        url = _LOCAL_TMPL.format(port=self._port)
        self._bus.publish_sync(self._tile_topic, url)
        self._log_line(f"Map → local tiles  {url}")

    def _switch_to_satellite(self) -> None:
        self._bus.publish_sync(self._tile_topic, _SAT_URL)
        self._log_line("Map → satellite (ArcGIS)")
