from __future__ import annotations

from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from src.controller.event_bus import EventBus
from src.controller.sar_recorder import SARRecorder
from src.views import theme


class _Emitter(QObject):
    status      = Signal(bool, int, int)   # recording, path_n, opi_n
    log_line    = Signal(str)
    export_done = Signal(bool, str)        # ok, message
    upload_done = Signal(bool, str)


class SARExportWidget(QWidget):
    """
    SAR trial data recorder and file exporter.

    Subscribes to path / OPI events via SARRecorder, then exports
    the four required SAR files and optionally uploads them to a WebDAV server.
    """

    def __init__(self, config: dict, event_bus: EventBus | None = None, parent=None):
        super().__init__(parent)
        self._cfg      = config
        self._event_bus = event_bus or EventBus()
        self._files:   dict[str, str] = {}
        self._emitter  = _Emitter()

        self._recorder = SARRecorder(self._event_bus, config)
        self._recorder.add_status_cb(lambda *a: self._emitter.status.emit(*a))
        self._recorder.add_log_cb(lambda m: self._emitter.log_line.emit(m))

        self._emitter.status.connect(self._on_status)
        self._emitter.log_line.connect(self._append_log)
        self._emitter.export_done.connect(self._on_export_done)
        self._emitter.upload_done.connect(self._on_upload_done)

        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG_PANEL}; color: {theme.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("◆ SAR EXPORT")
        title.setStyleSheet(
            f"color: {theme.CYAN}; font-size: 12px; font-family: 'Courier New'; "
            "letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep)

        # Status row
        self._rec_dot      = QLabel("●")
        self._status_path  = QLabel("PATH: 0 pts")
        self._status_opi   = QLabel("OPIs: 0")
        self._rec_dot.setFixedWidth(18)
        self._rec_dot.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 16px; background: transparent;"
        )
        for lbl in (self._status_path, self._status_opi):
            lbl.setStyleSheet(
                f"color: {theme.TEXT_DIM}; font-size: 11px; "
                "font-family: 'Courier New'; background: transparent;"
            )
        stat = QHBoxLayout()
        stat.addWidget(self._rec_dot)
        stat.addWidget(self._status_path, 1)
        stat.addWidget(self._status_opi)
        root.addLayout(stat)

        # REC / CLEAR
        rec_row = QHBoxLayout(); rec_row.setSpacing(6)
        self._rec_btn = QPushButton("● REC")
        self._rec_btn.setMinimumHeight(48)
        self._rec_btn.setStyleSheet(_btn_style("#ff4444", large=True))
        self._rec_btn.clicked.connect(self._toggle_recording)

        self._clear_btn = QPushButton("CLEAR")
        self._clear_btn.setMinimumHeight(48)
        self._clear_btn.setStyleSheet(_btn_style(theme.TEXT_DIM))
        self._clear_btn.clicked.connect(self._recorder.clear)

        rec_row.addWidget(self._rec_btn)
        rec_row.addWidget(self._clear_btn)
        root.addLayout(rec_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep2)

        # Output directory
        self._outdir = QLineEdit(str(self._cfg.get("output_dir", "sar_export")))
        self._outdir.setStyleSheet(_input_style())
        root.addLayout(self._field("Output", self._outdir))

        # WebDAV config
        dav_hdr = QLabel("WEBDAV SERVER")
        dav_hdr.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; "
            "letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(dav_hdr)

        self._dav_url  = QLineEdit(str(self._cfg.get("webdav_url",      "")))
        self._dav_user = QLineEdit(str(self._cfg.get("webdav_user",     "")))
        self._dav_pass = QLineEdit(str(self._cfg.get("webdav_password", "")))
        self._dav_pass.setEchoMode(QLineEdit.EchoMode.Password)
        for w in (self._dav_url, self._dav_user, self._dav_pass):
            w.setStyleSheet(_input_style())
        root.addLayout(self._field("URL",  self._dav_url))
        root.addLayout(self._field("User", self._dav_user))
        root.addLayout(self._field("Pass", self._dav_pass))

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep3)

        # Export / Upload
        act = QHBoxLayout(); act.setSpacing(6)
        self._export_btn = QPushButton("EXPORT FILES")
        self._export_btn.setMinimumHeight(54)
        self._export_btn.setStyleSheet(_btn_style(theme.CYAN, large=True))
        self._export_btn.clicked.connect(self._do_export)

        self._upload_btn = QPushButton("UPLOAD")
        self._upload_btn.setMinimumHeight(54)
        self._upload_btn.setEnabled(False)
        self._upload_btn.setStyleSheet(_btn_style("#44aaff", large=True))
        self._upload_btn.clicked.connect(self._do_upload)

        act.addWidget(self._export_btn)
        act.addWidget(self._upload_btn)
        root.addLayout(act)

        # Log
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            f"background: {theme.BG_DARK}; color: {theme.TEXT}; "
            "font-family: 'Courier New'; font-size: 10px; border: none;"
        )
        self._log.setMaximumBlockCount(400)
        root.addWidget(self._log, 1)

        clr = QPushButton("CLEAR LOG")
        clr.setMinimumHeight(32)
        clr.setStyleSheet(_btn_style(theme.TEXT_DIM))
        clr.clicked.connect(self._log.clear)
        root.addWidget(clr)

    def _field(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(10)
        lbl = QLabel(label)
        lbl.setFixedWidth(48)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 11px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    # ── Slots ──────────────────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        if self._recorder.is_recording:
            self._recorder.stop()
        else:
            self._recorder.start()

    def _on_status(self, recording: bool, path_n: int, opi_n: int) -> None:
        color = "#ff4444" if recording else theme.TEXT_DIM
        self._rec_dot.setStyleSheet(
            f"color: {color}; font-size: 16px; background: transparent;"
        )
        self._rec_btn.setText("■ STOP REC" if recording else "● REC")
        self._status_path.setText(f"PATH: {path_n} pts")
        self._status_opi.setText(f"OPIs: {opi_n}")

    def _do_export(self) -> None:
        self._export_btn.setEnabled(False)
        self._upload_btn.setEnabled(False)
        self._files = {}
        out = self._outdir.text().strip() or "sar_export"
        self._append_log(f"Exporting to {out}/ …")

        def _on_done(ok: bool, files: dict, err: str | None) -> None:
            self._files = files or {}
            if ok:
                self._emitter.export_done.emit(True, f"{len(self._files)} file(s) in {out}/")
            else:
                self._emitter.export_done.emit(False, str(err))

        self._recorder.export(
            out,
            on_progress=lambda m: self._emitter.log_line.emit(m),
            on_done=_on_done,
        )

    def _on_export_done(self, ok: bool, msg: str) -> None:
        self._export_btn.setEnabled(True)
        if ok:
            self._append_log(f"✓ Export done — {msg}")
            self._upload_btn.setEnabled(bool(self._dav_url.text().strip()))
        else:
            self._append_log(f"✗ Export failed: {msg}")

    def _do_upload(self) -> None:
        url = self._dav_url.text().strip()
        if not url or not self._files:
            self._append_log("No files to upload or no WebDAV URL configured.")
            return
        self._upload_btn.setEnabled(False)
        self._append_log(f"Uploading {len(self._files)} file(s) to {url} …")

        self._recorder.upload(
            self._files,
            url,
            username=self._dav_user.text(),
            password=self._dav_pass.text(),
            on_progress=lambda m: self._emitter.log_line.emit(m),
            on_done=lambda ok, err: self._emitter.upload_done.emit(ok, str(err) if not ok else ""),
        )

    def _on_upload_done(self, ok: bool, msg: str) -> None:
        self._upload_btn.setEnabled(bool(self._files and self._dav_url.text().strip()))
        if ok:
            self._append_log("✓ Upload complete")
        else:
            self._append_log(f"✗ Upload failed: {msg}")

    def _append_log(self, text: str) -> None:
        self._log.appendPlainText(text)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())


# ── Style helpers ─────────────────────────────────────────────────────────────

def _input_style() -> str:
    return (
        f"background: {theme.BG_DARK}; color: {theme.TEXT}; "
        f"border: 1px solid {theme.BORDER}; border-radius: 3px; "
        "padding: 6px 10px; font-size: 13px; font-family: 'Courier New'; "
        "min-height: 36px;"
    )


def _btn_style(accent: str = "", large: bool = False) -> str:
    c       = accent or theme.TEXT_DIM
    padding = "12px 24px" if large else "8px 18px"
    fsize   = "14px"      if large else "12px"
    border  = f"2px solid {theme.BORDER_DIM}" if large else f"1px solid {theme.BORDER_DIM}"
    return (
        f"QPushButton {{ background: {theme.BG_DARK}; color: {c}; "
        f"border: {border}; border-radius: 4px; padding: {padding}; "
        f"font-size: {fsize}; font-weight: bold; font-family: 'Courier New'; }}"
        f"QPushButton:hover {{ border-color: {c}; background: {theme.BG_SURFACE}; }}"
        f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
        f"QPushButton:disabled {{ color: {theme.TEXT_DIM}; border-color: {theme.BORDER_DIM}; }}"
    )
