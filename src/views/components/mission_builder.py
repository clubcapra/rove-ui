from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFrame,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QStackedWidget, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QVBoxLayout, QWidget,
)

from src.controller.event_bus import EventBus
from src.views import theme

# ── Manifest constants ────────────────────────────────────────────────────────

_CATEGORY_ORDER = ["flow", "navigation", "observation", "arm", "system", "fun"]
_CATEGORY_LABELS = {
    "flow":        "FLOW CONTROL",
    "navigation":  "NAVIGATION",
    "observation": "OBSERVATION",
    "arm":         "ARM",
    "system":      "SYSTEM",
    "fun":         "FUN",
}
_TRANSITION_LABELS = {
    "until_done_next": "DONE → NEXT",
    "until_done_end":  "DONE → END",
    "until_stopped":   "∞ UNTIL STOPPED",
    "loop_n":          "↺ LOOP N×",
}
_TRANSITION_PROTO = {
    "until_done_next": "UNTIL_DONE_NEXT",
    "until_done_end":  "UNTIL_DONE_END",
    "until_stopped":   "UNTIL_STOPPED",
    "loop_n":          "LOOP_N",
}

# ── Style helpers ─────────────────────────────────────────────────────────────

_INPUT = (
    f"background: {theme.BG_SURFACE}; color: {theme.TEXT}; "
    f"border: 1px solid {theme.BORDER}; border-radius: 0; "
    f"font-family: 'Courier New'; font-size: 10px; "
    f"padding: 2px 6px; min-height: 22px;"
)

_COMBO_DROPDOWN = (
    f"QComboBox {{ {_INPUT} }}"
    f"QComboBox::drop-down {{ border: none; }}"
    f"QComboBox QAbstractItemView {{"
    f"  background: {theme.BG_PANEL}; color: {theme.TEXT};"
    f"  border: 1px solid {theme.BORDER};"
    f"  selection-background-color: {theme.BG_SURFACE}; selection-color: {theme.CYAN};"
    f"}}"
)


def _section_label(text: str) -> QWidget:
    w = QWidget()
    w.setFixedHeight(22)
    w.setStyleSheet(f"background: {theme.BG_DEEP};")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(10, 0, 10, 0)
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {theme.TEXT_DIM}; font-size: 8px; letter-spacing: 2px; background: transparent;"
    )
    lay.addWidget(lbl)
    return w


def _divider() -> QWidget:
    w = QWidget()
    w.setFixedHeight(1)
    w.setStyleSheet(f"background: {theme.BORDER_DIM};")
    return w


# ── Touch-friendly keyboard text input ───────────────────────────────────────

class _TouchText(QPushButton):
    """Input-styled button that opens the virtual keyboard on tap."""

    def __init__(self, value: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        self._value = value
        self._placeholder = placeholder
        self._refresh()
        self.clicked.connect(self._open_kb)

    def _refresh(self) -> None:
        dim = not bool(self._value)
        display = self._value if not dim else (self._placeholder or "TAP TO ENTER")
        super().setText(display)
        c = theme.TEXT_DIM if dim else theme.TEXT
        self.setStyleSheet(
            f"QPushButton {{ {_INPUT} color: {c}; text-align: left; }}"
            f"QPushButton:hover {{ border-color: {theme.CYAN}; }}"
            f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
        )

    def _open_kb(self) -> None:
        from src.views.components.bitmap import _NamePicker
        from PySide6.QtWidgets import QDialog
        kb = _NamePicker(self._value, self.window())
        if kb.exec() == QDialog.DialogCode.Accepted:
            self._value = kb.name()
            self._refresh()

    def text(self) -> str:
        return self._value

    def setValue(self, v: str) -> None:
        self._value = v
        self._refresh()


# ── Param editor factory ──────────────────────────────────────────────────────

def _make_param_editor(
    param_def: dict,
    current_value: Any,
    variables: list[str],
) -> tuple[QWidget, "callable[[], Any]"]:
    """Returns (widget, get_value_fn) for one manifest param."""
    ptype   = param_def.get("type", "string")
    accepts = param_def.get("accepts", [])

    # ── enum ──────────────────────────────────────────────────────────────────
    if ptype == "enum":
        values = param_def.get("values", [])
        cb = QComboBox()
        cb.setStyleSheet(_COMBO_DROPDOWN)
        for v in values:
            cb.addItem(v, v)
        default = param_def.get("default", values[0] if values else "")
        sel = current_value if current_value in values else default
        if sel in values:
            cb.setCurrentIndex(values.index(sel))
        return cb, cb.currentData

    # ── number ────────────────────────────────────────────────────────────────
    if ptype == "number":
        spin = QDoubleSpinBox()
        spin.setStyleSheet(f"QDoubleSpinBox {{ {_INPUT} }}")
        spin.setRange(float(param_def.get("min", -1e9)), float(param_def.get("max", 1e9)))
        spin.setDecimals(2)
        unit = param_def.get("unit", "")
        if unit:
            spin.setSuffix(f" {unit}")
        val = current_value if current_value is not None else param_def.get("default", 0)
        try:
            spin.setValue(float(val))
        except (TypeError, ValueError):
            pass
        return spin, spin.value

    # ── string ────────────────────────────────────────────────────────────────
    if ptype == "string":
        le = _TouchText(
            str(current_value) if current_value else "",
            placeholder=param_def.get("name", ""),
        )
        return le, le.text

    # ── ref ───────────────────────────────────────────────────────────────────
    if ptype == "ref":
        has_coord = "map_coordinate" in accepts
        has_var   = any(a.startswith("variable:") for a in accepts)

        container = QWidget()
        container.setStyleSheet("background: transparent;")

        if has_coord and has_var:
            col = QVBoxLayout(container)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)

            type_cb = QComboBox()
            type_cb.setStyleSheet(_COMBO_DROPDOWN)
            type_cb.addItem("coordinate", "coord")
            type_cb.addItem("variable",   "var")

            stack = QStackedWidget()
            stack.setStyleSheet("background: transparent;")

            coord_w, lat_sp, lon_sp = _coord_widget(current_value if isinstance(current_value, dict) else None)
            var_w,   var_cb         = _variable_widget(variables, current_value if isinstance(current_value, str) else None)

            stack.addWidget(coord_w)
            stack.addWidget(var_w)
            type_cb.currentIndexChanged.connect(stack.setCurrentIndex)

            if isinstance(current_value, str) and current_value.startswith("$"):
                type_cb.setCurrentIndex(1)

            col.addWidget(type_cb)
            col.addWidget(stack)

            def _get_ref():
                if type_cb.currentData() == "coord":
                    return {"lat": lat_sp.value(), "lon": lon_sp.value(), "alt": 0.0}
                return var_cb.currentData()

            return container, _get_ref

        if has_coord:
            coord_w, lat_sp, lon_sp = _coord_widget(current_value if isinstance(current_value, dict) else None)
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addWidget(coord_w)
            return container, lambda: {"lat": lat_sp.value(), "lon": lon_sp.value(), "alt": 0.0}

        if has_var:
            var_w, var_cb = _variable_widget(variables, current_value if isinstance(current_value, str) else None)
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addWidget(var_w)
            return container, var_cb.currentData

        lbl = QLabel("(unsupported ref)")
        lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 9px;")
        return lbl, lambda: None

    # ── point_list ────────────────────────────────────────────────────────────
    if ptype == "point_list":
        outer = QWidget()
        outer.setStyleSheet("background: transparent;")
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(3)

        rows_container = QWidget()
        rows_container.setStyleSheet("background: transparent;")
        rows_lay = QVBoxLayout(rows_container)
        rows_lay.setContentsMargins(0, 0, 0, 0)
        rows_lay.setSpacing(3)

        # (row_widget, idx_label, lat_spinbox, lon_spinbox)
        rows_data: list[tuple[QWidget, QLabel, QDoubleSpinBox, QDoubleSpinBox]] = []

        def _renumber() -> None:
            for i, (_, lbl, _, _) in enumerate(rows_data):
                lbl.setText(f"P{i + 1}")

        def _remove_row(row_w: QWidget, lat_sp: QDoubleSpinBox, lon_sp: QDoubleSpinBox) -> None:
            for i, (rw, _, l, o) in enumerate(rows_data):
                if rw is row_w:
                    rows_data.pop(i)
                    rows_lay.removeWidget(row_w)
                    row_w.setParent(None)  # type: ignore[call-overload]
                    row_w.deleteLater()
                    break
            _renumber()

        def _add_row(lat_val: float = 0.0, lon_val: float = 0.0) -> None:
            row_w = QWidget()
            row_w.setStyleSheet(
                f"background: {theme.BG_DARK}; border: 1px solid {theme.BORDER_DIM}; border-radius: 2px;"
            )
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(6, 3, 3, 3)
            row_lay.setSpacing(4)

            idx_lbl = QLabel(f"P{len(rows_data) + 1}")
            idx_lbl.setFixedWidth(24)
            idx_lbl.setStyleSheet(
                f"color: {theme.CYAN}; font-size: 10px; font-weight: 700; "
                f"font-family: 'Courier New'; background: transparent; border: none;"
            )

            lat_sp = QDoubleSpinBox()
            lon_sp = QDoubleSpinBox()
            for sp, pfx, lo, hi in ((lat_sp, "lat ", -90, 90), (lon_sp, "lon ", -180, 180)):
                sp.setStyleSheet(f"QDoubleSpinBox {{ {_INPUT} }}")
                sp.setRange(lo, hi)
                sp.setDecimals(6)
                sp.setPrefix(pfx)
            lat_sp.setValue(lat_val)
            lon_sp.setValue(lon_val)

            rm_btn = QPushButton("✕")
            rm_btn.setFixedSize(22, 22)
            rm_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {theme.TEXT_DIM}; "
                f"border: none; font-size: 11px; padding: 0; }}"
                f"QPushButton:hover {{ color: #ff4444; }}"
            )
            rm_btn.clicked.connect(
                lambda _=False, rw=row_w, l=lat_sp, o=lon_sp: _remove_row(rw, l, o)
            )

            row_lay.addWidget(idx_lbl)
            row_lay.addWidget(lat_sp, 1)
            row_lay.addWidget(lon_sp, 1)
            row_lay.addWidget(rm_btn)

            rows_data.append((row_w, idx_lbl, lat_sp, lon_sp))
            rows_lay.addWidget(row_w)

        # Populate from current value (list of dicts) or start with 2 empty points
        init_pts = current_value if isinstance(current_value, list) else []
        for pt in init_pts:
            if isinstance(pt, dict):
                _add_row(float(pt.get("lat", 0.0)), float(pt.get("lon", 0.0)))
        while len(rows_data) < 2:
            _add_row()

        add_btn = QPushButton("＋  ADD POINT")
        add_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_DARK}; color: {theme.CYAN}; "
            f"border: 1px dashed {theme.BORDER_DIM}; border-radius: 2px; "
            f"font-size: 10px; font-family: 'Courier New'; padding: 5px; }}"
            f"QPushButton:hover {{ border-color: {theme.CYAN}; }}"
            f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
        )
        add_btn.clicked.connect(lambda: _add_row())

        outer_lay.addWidget(rows_container)
        outer_lay.addWidget(add_btn)

        def _get_points() -> list:
            return [
                {"lat": l.value(), "lon": o.value(), "alt": 0.0}
                for _, _, l, o in rows_data
            ]

        return outer, _get_points

    # ── route / geometry ──────────────────────────────────────────────────────
    if ptype in ("route", "geometry"):
        lbl = QLabel(f"({ptype}: define via map — not yet editable here)")
        lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 9px;")
        return lbl, lambda: current_value

    # ── fallback string ───────────────────────────────────────────────────────
    le = _TouchText(str(current_value) if current_value else "")
    return le, le.text


def _coord_widget(current: dict | None) -> tuple[QWidget, QDoubleSpinBox, QDoubleSpinBox]:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    lat = QDoubleSpinBox()
    lon = QDoubleSpinBox()
    for sp, pfx, lo, hi in ((lat, "lat ", -90, 90), (lon, "lon ", -180, 180)):
        sp.setStyleSheet(f"QDoubleSpinBox {{ {_INPUT} }}")
        sp.setRange(lo, hi)
        sp.setDecimals(6)
        sp.setPrefix(pfx)
    if isinstance(current, dict):
        lat.setValue(float(current.get("lat", 0.0)))
        lon.setValue(float(current.get("lon", 0.0)))
    row.addWidget(lat, 1)
    row.addWidget(lon, 1)
    return w, lat, lon


def _variable_widget(variables: list[str], current: str | None) -> tuple[QWidget, QComboBox]:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    cb = QComboBox()
    cb.setStyleSheet(_COMBO_DROPDOWN)
    if not variables:
        cb.addItem("(no variables declared)", None)
    for v in variables:
        cb.addItem(v, v)
    if current and current in variables:
        cb.setCurrentIndex(variables.index(current))
    col.addWidget(cb)
    return w, cb


# ── Step list delegate ────────────────────────────────────────────────────────

def _params_summary(step: dict) -> str:
    parts = []
    for k, v in step.get("params", {}).items():
        if v is None:
            parts.append(f"{k}: ?")
        elif isinstance(v, dict) and "lat" in v:
            parts.append(f"{k}: ({v['lat']:.4f}, {v['lon']:.4f})")
        else:
            s = str(v)
            parts.append(f"{k}: {s[:18]}")
    return "  ·  ".join(parts) or "—"


class _StepDelegate(QStyledItemDelegate):
    ITEM_H = 58

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(0, self.ITEM_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        step = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(step, dict):
            super().paint(painter, option, index)
            return

        is_sel = bool(option.state & QStyle.StateFlag.State_Selected)
        r      = option.rect

        painter.fillRect(r, QColor(theme.BG_SURFACE if is_sel else theme.BG_DARK))

        if is_sel:
            painter.fillRect(r.x(), r.y(), 3, r.height(), QColor(theme.CYAN))

        row_n = index.row() + 1
        cmd   = step.get("command", "")

        # Row number badge
        painter.setFont(QFont("Courier New", 8))
        painter.setPen(QColor(theme.TEXT_DIM))
        num_rect = r.adjusted(10, 0, 0, 0)
        num_rect.setWidth(24)
        painter.drawText(num_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{row_n:02d}")

        # Command name
        painter.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        painter.setPen(QColor(theme.CYAN if is_sel else theme.TEXT))
        name_rect = r.adjusted(38, 6, -120, -r.height() // 2)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"◆  {cmd.upper()}")

        # Params summary
        painter.setFont(QFont("Courier New", 8))
        painter.setPen(QColor(theme.TEXT_DIM))
        sum_rect = r.adjusted(38, r.height() // 2 + 2, -120, -4)
        painter.drawText(sum_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         _params_summary(step))

        # Transition badge (right-aligned)
        tr      = step.get("transition", "until_done_next")
        tr_lbl  = _TRANSITION_LABELS.get(tr, tr)
        painter.setFont(QFont("Courier New", 7))
        painter.setPen(QColor(theme.TEXT_DIM))
        badge_rect = r.adjusted(r.width() - 118, 0, -6, 0)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tr_lbl)

        # Bottom border
        painter.setPen(QPen(QColor(theme.BORDER_DIM), 1))
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())


# ── Palette block card ────────────────────────────────────────────────────────

class _BlockCard(QFrame):
    def __init__(self, cmd_def: dict, on_click, on_double_click, parent=None):
        super().__init__(parent)
        self._cmd            = cmd_def
        self._on_click       = on_click
        self._on_double_click = on_double_click
        self._selected       = False

        self.setFixedHeight(52)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._refresh_style()

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        dot = QLabel("◆")
        dot.setFixedWidth(14)
        dot.setStyleSheet(f"font-size: 8px; color: {theme.CYAN}; background: transparent;")

        col = QVBoxLayout()
        col.setSpacing(1)

        name_lbl = QLabel(cmd_def["id"].upper())
        name_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {theme.TEXT}; "
            f"font-family: 'Courier New'; background: transparent;"
        )
        desc = (cmd_def.get("desc", "") or "")[:64]
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"font-size: 9px; color: {theme.TEXT_DIM}; font-family: 'Courier New'; background: transparent;"
        )

        col.addWidget(name_lbl)
        col.addWidget(desc_lbl)

        row.addWidget(dot)
        row.addLayout(col, 1)

    def _refresh_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"_BlockCard {{ background: {theme.BG_SURFACE}; outline: none; "
                f"border: none; border-left: 3px solid {theme.CYAN}; "
                f"border-bottom: 1px solid {theme.BORDER_DIM}; }}"
            )
        else:
            self.setStyleSheet(
                f"_BlockCard {{ background: {theme.BG_DARK}; outline: none; "
                f"border: none; border-bottom: 1px solid {theme.BORDER_DIM}; }}"
                f"_BlockCard:hover {{ background: {theme.BG_SURFACE}; }}"
            )

    def set_selected(self, val: bool) -> None:
        self._selected = val
        self._refresh_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self._cmd)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_double_click(self._cmd)
        super().mouseDoubleClickEvent(event)


# ── Mission builder ───────────────────────────────────────────────────────────

class MissionBuilder:
    """
    Two-panel mission composer.

    Left  — scrollable command palette (grouped by category).
    Right — step sequence (drag-to-reorder) + inline param editor.

    Config keys:
      manifest_path  str   path to mission_manifest.json (relative to project root)
      send_topic     str   event-bus topic for the serialized mission (default "mission.send")
    """

    def __init__(self, name: str, config: dict, event_bus: EventBus | None = None):
        self.name       = name
        self.config     = config or {}
        self.event_bus  = event_bus or EventBus()
        self._manifest: dict = {}
        self._widget: QWidget | None = None

        # palette state
        self._palette_cards: list[_BlockCard] = []
        self._selected_cmd: dict | None       = None

        # edit-panel state
        self._step_list:     QListWidget | None = None
        self._edit_scroll:   QScrollArea | None = None
        self._edit_inner:    QWidget | None      = None
        self._edit_title:    QLabel | None       = None
        self._remove_btn:    QPushButton | None  = None
        self._name_input:    _TouchText | None   = None
        self._param_getters: dict[str, "callable[[], Any]"] = {}
        self._tr_combo:      QComboBox | None    = None
        self._loop_spin:     QSpinBox | None     = None
        self._loop_row:      QWidget | None      = None

        self._load_manifest()

    # ── Manifest ──────────────────────────────────────────────────────────────

    def _load_manifest(self) -> None:
        path = str(self.config.get("manifest_path", "mission_manifest.json")).strip()
        p = Path(path) if Path(path).is_absolute() else Path(__file__).resolve().parents[3] / path
        try:
            with open(p, "r", encoding="utf-8") as f:
                self._manifest = json.load(f)
            return
        except Exception as e:
            self.event_bus.publish_sync("log", f"[MissionBuilder] manifest '{path}' → {e}")
        self._manifest = self.config.get("manifest", {})

    # ── Build ─────────────────────────────────────────────────────────────────

    def build(self) -> None:
        if self._widget is not None:
            return

        root = QWidget()
        root.setStyleSheet(f"background: {theme.BG_DEEP};")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_palette())
        lay.addWidget(self._build_add_column())
        lay.addWidget(self._build_mission_panel(), 1)

        self._widget = root

        # Subscribe to step requests from other views (e.g. map action wheel)
        step_topic = str(self.config.get("mission_step_topic", "mission.step_request")).strip()
        self.event_bus.subscribe(step_topic, self._on_step_request)

    # ── Palette ───────────────────────────────────────────────────────────────

    def _build_palette(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(262)
        w.setStyleSheet(f"background: {theme.BG_DARK}; border-right: 1px solid {theme.BORDER_DIM};")

        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"background: {theme.BG_PANEL}; border-bottom: 1px solid {theme.BORDER_DIM};"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 0, 10, 0)
        hdr_lay.setSpacing(6)
        for t, s in (
            ("◆", f"color:{theme.CYAN};font-size:9px;font-weight:700;background:transparent;"),
            ("COMMAND PALETTE", f"color:{theme.TEXT_DIM};font-size:10px;letter-spacing:1.5px;background:transparent;"),
        ):
            lbl = QLabel(t); lbl.setStyleSheet(s); hdr_lay.addWidget(lbl)
        hdr_lay.addStretch()
        col.addWidget(hdr)

        # Cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {theme.BG_DARK}; }}")

        inner = QWidget()
        inner.setStyleSheet(f"background: {theme.BG_DARK};")
        inner_col = QVBoxLayout(inner)
        inner_col.setContentsMargins(0, 4, 0, 4)
        inner_col.setSpacing(0)

        by_cat: dict[str, list[dict]] = {}
        for cmd in self._manifest.get("commands", []):
            if not cmd.get("available", True):
                continue
            by_cat.setdefault(cmd.get("category", "system"), []).append(cmd)

        for cat in _CATEGORY_ORDER:
            cmds = by_cat.get(cat, [])
            if not cmds:
                continue
            inner_col.addWidget(_section_label(_CATEGORY_LABELS.get(cat, cat.upper())))
            for cmd in cmds:
                card = _BlockCard(cmd, self._on_palette_select, self._on_add_step)
                self._palette_cards.append(card)
                inner_col.addWidget(card)

        inner_col.addStretch()
        scroll.setWidget(inner)
        col.addWidget(scroll, 1)
        return w

    # ── Add column ────────────────────────────────────────────────────────────

    def _build_add_column(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(42)
        w.setStyleSheet(f"background: {theme.BG_DEEP};")

        col = QVBoxLayout(w)
        col.setContentsMargins(5, 0, 5, 0)
        col.addStretch()

        self._add_btn = QPushButton("→")
        self._add_btn.setToolTip("Add selected block (or double-click a block)")
        self._add_btn.setFixedSize(32, 32)
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.CYAN}; color: {theme.BG_DEEP}; "
            f"border: none; font-size: 16px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #ffc840; }}"
            f"QPushButton:pressed {{ background: {theme.AMBER}; }}"
            f"QPushButton:disabled {{ background: {theme.BG_SURFACE}; color: {theme.TEXT_DIM}; }}"
        )
        self._add_btn.clicked.connect(self._on_add_btn_click)
        col.addWidget(self._add_btn)
        col.addStretch()
        return w

    # ── Mission panel ─────────────────────────────────────────────────────────

    def _build_mission_panel(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # Header bar
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"background: {theme.BG_PANEL}; border-bottom: 1px solid {theme.BORDER_DIM};"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 0, 10, 0)
        hdr_lay.setSpacing(8)

        for t, s in (
            ("◆", f"color:{theme.CYAN};font-size:9px;font-weight:700;background:transparent;"),
            ("MISSION SEQUENCE", f"color:{theme.TEXT_DIM};font-size:10px;letter-spacing:1.5px;background:transparent;"),
        ):
            lbl = QLabel(t); lbl.setStyleSheet(s); hdr_lay.addWidget(lbl)

        hdr_lay.addStretch()

        self._name_input = _TouchText("Mission 1")
        self._name_input.setFixedHeight(22)
        self._name_input.setFixedWidth(160)
        hdr_lay.addWidget(self._name_input)

        send_btn = QPushButton("◆  SEND MISSION")
        send_btn.setFixedHeight(24)
        send_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.CYAN}; color: {theme.BG_DEEP}; border: none; "
            f"font-weight: 700; font-size: 10px; letter-spacing: 1.5px; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: #ffc840; }}"
        )
        send_btn.clicked.connect(self._on_send)
        hdr_lay.addWidget(send_btn)

        col.addWidget(hdr)

        # Step list
        self._step_list = QListWidget()
        self._step_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._step_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._step_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._step_list.setStyleSheet(
            f"QListWidget {{ background: {theme.BG_DARK}; border: none; outline: none; }}"
            f"QListWidget::item {{ background: transparent; border: none; }}"
            f"QListWidget::item:selected {{ background: {theme.BG_SURFACE}; }}"
        )
        self._step_list.setItemDelegate(_StepDelegate(self._step_list))
        self._step_list.currentItemChanged.connect(self._on_step_selected)
        # Refresh row-number badges after drag-drop
        self._step_list.model().rowsMoved.connect(
            lambda *_: self._step_list.viewport().update()
        )
        col.addWidget(self._step_list, 3)

        col.addWidget(self._build_edit_panel(), 2)
        return w

    # ── Edit panel ────────────────────────────────────────────────────────────

    def _build_edit_panel(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(
            f"QWidget {{ background: {theme.BG_PANEL}; border-top: 1px solid {theme.BORDER_DIM}; }}"
        )
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # Edit header
        hdr = QWidget()
        hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background: {theme.BG_DARK}; border-bottom: 1px solid {theme.BORDER_DIM};"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 0, 10, 0)
        hdr_lay.setSpacing(0)

        self._edit_title = QLabel("SELECT A STEP TO CONFIGURE")
        self._edit_title.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 9px; letter-spacing: 1.5px; background: transparent;"
        )
        hdr_lay.addWidget(self._edit_title)
        hdr_lay.addStretch()

        self._remove_btn = QPushButton("✗  REMOVE STEP")
        self._remove_btn.setFixedHeight(20)
        self._remove_btn.setVisible(False)
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.RED}; "
            f"border: 1px solid rgba(255,61,61,0.35); font-size: 9px; letter-spacing: 1px; padding: 0 8px; }}"
            f"QPushButton:hover {{ background: rgba(255,61,61,0.10); border-color: {theme.RED}; }}"
        )
        self._remove_btn.clicked.connect(self._on_remove_step)
        hdr_lay.addWidget(self._remove_btn)

        col.addWidget(hdr)

        self._edit_scroll = QScrollArea()
        self._edit_scroll.setWidgetResizable(True)
        self._edit_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit_scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")
        col.addWidget(self._edit_scroll, 1)

        self._set_edit_inner(self._make_empty_inner())
        return container

    def _set_edit_inner(self, w: QWidget) -> None:
        old = self._edit_inner
        self._edit_scroll.setWidget(w)  # type: ignore[union-attr]
        self._edit_inner = w
        if old is not None:
            old.deleteLater()

    def _make_empty_inner(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("← double-click a block  or  select a step")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        lay.addWidget(lbl)
        return w

    def _make_step_inner(self, step: dict, cmd_def: dict) -> QWidget:
        self._param_getters.clear()
        self._tr_combo   = None
        self._loop_spin  = None
        self._loop_row   = None

        w = QWidget()
        w.setStyleSheet("background: transparent;")
        form = QVBoxLayout(w)
        form.setContentsMargins(14, 10, 14, 10)
        form.setSpacing(6)

        current_params = step.get("params", {})
        variables      = self._collect_variables()

        for param_def in cmd_def.get("params", []):
            pname    = param_def["name"]
            required = param_def.get("required", False)

            row = QHBoxLayout()
            row.setSpacing(10)

            lbl_text = pname + (" *" if required else "")
            lbl = QLabel(lbl_text)
            lbl.setFixedWidth(96)
            lbl.setStyleSheet(
                f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; background: transparent;"
            )
            editor, getter = _make_param_editor(param_def, current_params.get(pname), variables)
            self._param_getters[pname] = getter

            row.addWidget(lbl)
            row.addWidget(editor, 1)
            form.addLayout(row)

        # "binds" field if the command produces a variable
        if cmd_def.get("produces"):
            vtype = cmd_def["produces"].get("type", "entity")
            row   = QHBoxLayout()
            row.setSpacing(10)
            lbl = QLabel("bind as")
            lbl.setFixedWidth(96)
            lbl.setStyleSheet(
                f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; background: transparent;"
            )
            binds_le = _TouchText(step.get("binds", ""), placeholder=f"$my_{vtype}")
            self._param_getters["__binds__"] = binds_le.text
            row.addWidget(lbl)
            row.addWidget(binds_le, 1)
            form.addLayout(row)

        form.addWidget(_divider())

        # Transition selector
        valid_tr = cmd_def.get("valid_transitions", list(_TRANSITION_LABELS.keys()))
        tr_row   = QHBoxLayout()
        tr_row.setSpacing(10)

        tr_lbl = QLabel("transition")
        tr_lbl.setFixedWidth(96)
        tr_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; background: transparent;"
        )
        self._tr_combo = QComboBox()
        self._tr_combo.setStyleSheet(_COMBO_DROPDOWN)
        for tr_id in valid_tr:
            self._tr_combo.addItem(_TRANSITION_LABELS.get(tr_id, tr_id), tr_id)
        cur_tr = step.get("transition", valid_tr[0] if valid_tr else "until_done_next")
        for i in range(self._tr_combo.count()):
            if self._tr_combo.itemData(i) == cur_tr:
                self._tr_combo.setCurrentIndex(i)
                break
        self._tr_combo.currentIndexChanged.connect(self._on_tr_changed)
        tr_row.addWidget(tr_lbl)
        tr_row.addWidget(self._tr_combo, 1)
        form.addLayout(tr_row)

        # Loop count row (shown only when loop_n selected)
        self._loop_row = QWidget()
        self._loop_row.setStyleSheet("background: transparent;")
        loop_inner = QHBoxLayout(self._loop_row)
        loop_inner.setContentsMargins(0, 0, 0, 0)
        loop_inner.setSpacing(10)
        lp_lbl = QLabel("loop count")
        lp_lbl.setFixedWidth(96)
        lp_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; background: transparent;"
        )
        self._loop_spin = QSpinBox()
        self._loop_spin.setStyleSheet(f"QSpinBox {{ {_INPUT} }}")
        self._loop_spin.setRange(2, 999)
        self._loop_spin.setValue(int(step.get("loop_count", 3)))
        loop_inner.addWidget(lp_lbl)
        loop_inner.addWidget(self._loop_spin, 1)
        self._loop_row.setVisible(cur_tr == "loop_n")
        form.addWidget(self._loop_row)

        # Apply button
        apply_btn = QPushButton("◆  APPLY CHANGES")
        apply_btn.setFixedHeight(28)
        apply_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_SURFACE}; color: {theme.CYAN}; "
            f"border: 1px solid {theme.CYAN}; font-weight: 700; font-size: 10px; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ background: {theme.CYAN}; color: {theme.BG_DEEP}; }}"
        )
        apply_btn.clicked.connect(self._on_apply)
        form.addWidget(apply_btn)
        form.addStretch()
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_palette_select(self, cmd: dict) -> None:
        self._selected_cmd = cmd
        for card in self._palette_cards:
            card.set_selected(card._cmd is cmd)

    def _on_add_btn_click(self) -> None:
        if self._selected_cmd:
            self._on_add_step(self._selected_cmd)

    def _on_add_step(self, cmd: dict) -> None:
        step: dict = {
            "command":    cmd["id"],
            "params":     {p["name"]: p.get("default") for p in cmd.get("params", [])},
            "transition": (cmd.get("valid_transitions") or ["until_done_next"])[0],
            "loop_count": 3,
            "binds":      "",
        }
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, step)
        item.setSizeHint(QSize(0, _StepDelegate.ITEM_H))
        self._step_list.addItem(item)  # type: ignore[union-attr]
        self._step_list.setCurrentItem(item)  # type: ignore[union-attr]
        self.event_bus.publish_sync("log", f"[MissionBuilder] + {cmd['id']}")

    def _on_step_selected(self, current: QListWidgetItem, _previous: QListWidgetItem) -> None:
        if current is None:
            self._edit_title.setText("SELECT A STEP TO CONFIGURE")  # type: ignore[union-attr]
            self._remove_btn.setVisible(False)  # type: ignore[union-attr]
            self._set_edit_inner(self._make_empty_inner())
            return

        step    = current.data(Qt.ItemDataRole.UserRole)
        cmd_def = self._find_cmd(step.get("command", ""))
        idx     = self._step_list.currentRow() + 1  # type: ignore[union-attr]

        self._edit_title.setText(  # type: ignore[union-attr]
            f"STEP {idx:02d}  —  {step.get('command', '').upper()}"
        )
        self._remove_btn.setVisible(True)  # type: ignore[union-attr]
        self._set_edit_inner(
            self._make_step_inner(step, cmd_def) if cmd_def else self._make_empty_inner()
        )

    def _on_tr_changed(self) -> None:
        if self._tr_combo and self._loop_row:
            self._loop_row.setVisible(self._tr_combo.currentData() == "loop_n")

    def _on_apply(self) -> None:
        item = self._step_list.currentItem()  # type: ignore[union-attr]
        if item is None:
            return

        step = dict(item.data(Qt.ItemDataRole.UserRole))
        params: dict = {}
        for pname, getter in self._param_getters.items():
            if pname == "__binds__":
                step["binds"] = getter()
            else:
                params[pname] = getter()
        step["params"] = params

        if self._tr_combo:
            step["transition"] = self._tr_combo.currentData()
        if self._loop_spin and step.get("transition") == "loop_n":
            step["loop_count"] = self._loop_spin.value()

        item.setData(Qt.ItemDataRole.UserRole, step)
        self._step_list.viewport().update()  # type: ignore[union-attr]
        self.event_bus.publish_sync("log", f"[MissionBuilder] updated step {step['command']}")

    def _on_remove_step(self) -> None:
        row = self._step_list.currentRow()  # type: ignore[union-attr]
        if row >= 0:
            item = self._step_list.item(row)  # type: ignore[union-attr]
            if item:
                step = item.data(Qt.ItemDataRole.UserRole) or {}
                marker_id = step.get("map_marker_id", "")
                if marker_id:
                    self.event_bus.publish_sync("mission.marker_remove", {"id": marker_id})
            self._step_list.takeItem(row)  # type: ignore[union-attr]
            self._edit_title.setText("SELECT A STEP TO CONFIGURE")  # type: ignore[union-attr]
            self._remove_btn.setVisible(False)  # type: ignore[union-attr]
            self._set_edit_inner(self._make_empty_inner())

    def _on_send(self) -> None:
        mission = self._serialize()
        if not mission["sequence"]:
            self.event_bus.publish_sync("log", "[MissionBuilder] mission is empty — nothing sent")
            return
        topic = str(self.config.get("send_topic", "mission.send")).strip()
        self.event_bus.publish_sync(topic, mission)
        self.event_bus.publish_sync(
            "log",
            f"[MissionBuilder] sent '{mission['name']}' — {len(mission['sequence'])} steps",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect_variables(self) -> list[str]:
        seen: list[str] = []
        for i in range(self._step_list.count()):  # type: ignore[union-attr]
            b = self._step_list.item(i).data(Qt.ItemDataRole.UserRole).get("binds", "")  # type: ignore[union-attr]
            if b and b not in seen:
                seen.append(b)
        return seen

    def _find_cmd(self, cmd_id: str) -> dict | None:
        for cmd in self._manifest.get("commands", []):
            if cmd["id"] == cmd_id:
                return cmd
        return None

    def _serialize(self) -> dict:
        manifest = self._manifest
        variables: list[dict] = []
        sequence:  list[dict] = []

        # Collect variable declarations (first pass)
        var_types: dict[str, str] = {}
        for i in range(self._step_list.count()):  # type: ignore[union-attr]
            step    = self._step_list.item(i).data(Qt.ItemDataRole.UserRole)  # type: ignore[union-attr]
            binds   = step.get("binds", "").strip()
            if binds:
                cmd_def = self._find_cmd(step["command"])
                if cmd_def and cmd_def.get("produces"):
                    vtype = cmd_def["produces"].get("type", "entity").upper()
                    var_types.setdefault(binds, vtype)

        for vname, vtype in var_types.items():
            variables.append({"name": vname, "type": vtype})

        # Serialize steps (second pass)
        for i in range(self._step_list.count()):  # type: ignore[union-attr]
            step   = self._step_list.item(i).data(Qt.ItemDataRole.UserRole)  # type: ignore[union-attr]
            tr_key = step.get("transition", "until_done_next")

            params_list: list[dict] = []
            for pname, pval in step.get("params", {}).items():
                if pval is None:
                    continue
                val_msg = self._encode_value(pval)
                if val_msg is not None:
                    params_list.append({"name": pname, "value": val_msg})

            sequence.append({
                "command":    step["command"],
                "params":     params_list,
                "binds":      step.get("binds", ""),
                "transition": {
                    "type":       _TRANSITION_PROTO.get(tr_key, "UNTIL_DONE_NEXT"),
                    "loop_count": step.get("loop_count", 0) if tr_key == "loop_n" else 0,
                },
            })

        return {
            "schema_version": manifest.get("schema_version", 1),
            "firmware_hash":  manifest.get("firmware_hash", ""),
            "name":           self._name_input.text().strip() if self._name_input else "Mission",
            "variables":      variables,
            "sequence":       sequence,
        }

    @staticmethod
    def _encode_value(v: Any) -> dict | None:
        if isinstance(v, dict) and "lat" in v:
            return {"coordinate": {"lat": v["lat"], "lon": v.get("lon", 0.0), "alt": v.get("alt", 0.0)}}
        if isinstance(v, str):
            if v.startswith("$"):
                return {"variable_ref": v}
            return {"enum_value": v}
        if isinstance(v, bool):
            return {"flag": v}
        if isinstance(v, (int, float)):
            return {"number": float(v)}
        return None

    def _on_step_request(self, payload: Any) -> None:
        """Receive a step from an external source (e.g. map action wheel) and enqueue it."""
        if not isinstance(payload, dict):
            return
        command = str(payload.get("command", "")).strip()
        if not command:
            return
        cmd_def = self._find_cmd(command)
        if cmd_def is None:
            self.event_bus.publish_sync("log", f"[MissionBuilder] unknown command from map: {command}")
            return

        incoming_params = payload.get("params", {})
        step: dict = {
            "command":       command,
            "params":        {
                **{p["name"]: p.get("default") for p in cmd_def.get("params", [])},
                **incoming_params,
            },
            "transition":    (cmd_def.get("valid_transitions") or ["until_done_next"])[0],
            "loop_count":    3,
            "binds":         "",
            "map_marker_id": str(payload.get("map_marker_id", "")),
        }
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, step)
        item.setSizeHint(QSize(0, _StepDelegate.ITEM_H))
        if self._step_list is not None:
            self._step_list.addItem(item)
            self._step_list.scrollToItem(item)
        self.event_bus.publish_sync("log", f"[MissionBuilder] ← map: {command} ajouté")

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]
