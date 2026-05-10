from __future__ import annotations

import json
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.controller.event_bus import EventBus

TEMPLATE_PATH = Path(__file__).resolve().parent / "html" / "urdfViewer.html"
FALLBACK_HTML = "<html><body style='color:red;background:#111'>urdfViewer.html template missing</body></html>"


def _parse_floats(text: str) -> list[float]:
    try:
        return [float(v) for v in text.strip().split()]
    except Exception:
        return []


def _parse_xyz(text: str) -> list[float]:
    vals = _parse_floats(text)
    return (vals + [0.0, 0.0, 0.0])[:3]


def _normalize(v: list[float]) -> list[float]:
    mag = math.sqrt(sum(c * c for c in v))
    if mag < 1e-9:
        return [0.0, 0.0, 1.0]
    return [c / mag for c in v]


# ── URDF parser ────────────────────────────────────────────────────────────────

class URDFParser:
    def parse(self, urdf_path: Path) -> dict:
        tree = ET.parse(urdf_path)
        root = tree.getroot()
        mesh_dir = urdf_path.parent

        links: dict[str, dict] = {}
        for link_el in root.findall("link"):
            name = link_el.get("name", "")
            mesh_url: str | None = None
            visual = link_el.find("visual")
            if visual is not None:
                geom = visual.find("geometry")
                if geom is not None:
                    mesh_el = geom.find("mesh")
                    if mesh_el is not None:
                        filename = mesh_el.get("filename", "")
                        mesh_path = (mesh_dir / filename).resolve()
                        if mesh_path.exists():
                            mesh_url = QUrl.fromLocalFile(str(mesh_path)).toString()
            links[name] = {"mesh_url": mesh_url}

        joints: list[dict] = []
        for joint_el in root.findall("joint"):
            jname = joint_el.get("name", "")
            jtype = joint_el.get("type", "fixed")

            parent_el = joint_el.find("parent")
            child_el  = joint_el.find("child")
            if parent_el is None or child_el is None:
                continue
            parent = parent_el.get("link", "")
            child  = child_el.get("link", "")

            origin_el = joint_el.find("origin")
            urdf_xyz = _parse_xyz(origin_el.get("xyz", "0 0 0")) if origin_el is not None else [0.0, 0.0, 0.0]
            urdf_rpy = _parse_xyz(origin_el.get("rpy", "0 0 0")) if origin_el is not None else [0.0, 0.0, 0.0]

            axis_el  = joint_el.find("axis")
            urdf_axis = _normalize(_parse_xyz(axis_el.get("xyz", "0 0 1"))) if axis_el is not None else [0.0, 0.0, 1.0]

            limit: dict | None = None
            limit_el = joint_el.find("limit")
            if limit_el is not None and jtype == "revolute":
                limit = {
                    "lower": float(limit_el.get("lower", -math.pi)),
                    "upper": float(limit_el.get("upper",  math.pi)),
                }

            joints.append({
                "name":   jname,
                "type":   jtype,
                "parent": parent,
                "child":  child,
                "xyz":   urdf_xyz,   # raw URDF space — JS applies root correction rotation
                "rpy":   urdf_rpy,
                "axis":  urdf_axis,
                "limit": limit,
            })

        # Find the root link (not a child in any joint)
        children = {j["child"] for j in joints}
        root_link = next((name for name in links if name not in children), None)

        return {
            "root":   root_link,
            "links":  links,
            "joints": joints,
        }


# ── Qt plumbing ────────────────────────────────────────────────────────────────

class _URDFPage(QWebEnginePage):
    def __init__(self, event_bus: EventBus, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if message:
            self._event_bus.publish_sync("log", f"URDFViewer JS[{lineNumber}] {message}")
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)


class URDFViewer(QWidget):
    """Real-time URDF robot visualizer backed by Three.js.

    Config:
        urdf: str             relative or absolute path to the .urdf file
        controls:
            joint_angles:
              - joint: "joint_revolute_5"
                topic: "drive.fl_pos"
                scale: 1.0        # rad per unit (use 0.01745 for degrees)
                offset: 0.0
            robot_pose:
                roll_topic:  "gnss.roll"
                pitch_topic: "gnss.pitch"
                yaw_topic:   "gnss.yaw"
    """

    _js_queue: Signal = Signal(str)

    def __init__(self, name: str, config: dict[str, Any], event_bus: EventBus | None = None):
        super().__init__()
        self.name = name
        self._config = config or {}
        self._event_bus = event_bus or EventBus()
        self._view: QWebEngineView | None = None
        self._is_ready = False
        self._pending_scripts: list[str] = []
        self._html_file = Path(tempfile.gettempdir()) / f"urdf_viewer_{name}.html"
        self._project_root = Path(__file__).resolve().parents[3]
        self._js_queue.connect(self._exec_js)

    def build(self) -> None:
        urdf_rel = self._config.get("urdf", "")
        if not urdf_rel:
            self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: no 'urdf' key in config")
            return

        urdf_path = Path(urdf_rel)
        if not urdf_path.is_absolute():
            urdf_path = self._project_root / urdf_path
        if not urdf_path.exists():
            self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: URDF not found: {urdf_path}")
            return

        try:
            urdf_data = URDFParser().parse(urdf_path)
            n_links  = len(urdf_data["links"])
            n_joints = len(urdf_data["joints"])
            self._event_bus.publish_sync(
                "log", f"URDFViewer[{self.name}]: parsed {n_links} links, {n_joints} joints (root={urdf_data['root']})"
            )
        except Exception as exc:
            self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: URDF parse error: {exc}")
            return

        try:
            template = TEMPLATE_PATH.read_text(encoding="utf-8")
        except OSError:
            self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: template missing at {TEMPLATE_PATH}")
            template = FALLBACK_HTML

        urdf_data["link_colors"] = self._config.get("link_colors", {})
        urdf_json = json.dumps(urdf_data, separators=(",", ":"))
        html = template.replace("/* URDF_DATA_PLACEHOLDER */", f"window.URDF_DATA = {urdf_json};")
        self._html_file.write_text(html, encoding="utf-8")

        self._view = QWebEngineView()
        self._view.setPage(_URDFPage(self._event_bus, self._view))
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.load(QUrl.fromLocalFile(str(self._html_file)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    # ── Load finished ──────────────────────────────────────────────────────────

    def _on_load_finished(self, ok: bool) -> None:
        self._is_ready = bool(ok)
        if not ok:
            self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: HTML load failed")
            return
        self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: ready")
        for script in self._pending_scripts:
            self._view.page().runJavaScript(script)  # type: ignore[union-attr]
        self._pending_scripts.clear()
        self._register_bindings()

    # ── EventBus bindings ──────────────────────────────────────────────────────

    def _register_bindings(self) -> None:
        controls = self._config.get("controls", {})
        if not isinstance(controls, dict):
            return

        count = 0

        for binding in controls.get("joint_angles", []):
            if not isinstance(binding, dict):
                continue
            joint = str(binding.get("joint", "")).strip()
            topic = str(binding.get("topic", "")).strip()
            if not joint or not topic:
                continue
            scale  = float(binding.get("scale",  1.0))
            offset = float(binding.get("offset", 0.0))

            def _on_angle(value, j=joint, s=scale, off=offset):
                try:
                    angle = float(value) * s + off
                except (TypeError, ValueError):
                    return
                self.run_js(f"window.setJointAngle({json.dumps(j)}, {angle:.6f});")

            self._event_bus.subscribe(topic, _on_angle)
            count += 1

        pose_cfg = controls.get("robot_pose", {})
        if isinstance(pose_cfg, dict):
            for cfg_key, js_fn in (
                ("roll_topic",  "setRobotRoll"),
                ("pitch_topic", "setRobotPitch"),
                ("yaw_topic",   "setRobotYaw"),
            ):
                topic = str(pose_cfg.get(cfg_key, "")).strip()
                if not topic:
                    continue

                def _on_pose(value, fn=js_fn):
                    try:
                        angle = float(value) * (math.pi / 180.0)
                    except (TypeError, ValueError):
                        return
                    self.run_js(f"window.{fn}({angle:.6f});")

                self._event_bus.subscribe(topic, _on_pose)
                count += 1

        if count:
            self._event_bus.publish_sync("log", f"URDFViewer[{self.name}]: {count} binding(s) registered")

    # ── JS bridge ──────────────────────────────────────────────────────────────

    def run_js(self, script: str) -> None:
        if not self._view:
            return
        if not self._is_ready:
            self._pending_scripts.append(script)
            return
        self._js_queue.emit(script)

    @Slot(str)
    def _exec_js(self, script: str) -> None:
        if self._view:
            self._view.page().runJavaScript(script)
