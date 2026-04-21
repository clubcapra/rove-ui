import sys
import tempfile
import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Three.js Viewer</title>
    <style>
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: #1a1a2e;
        }
        #canvas-container {
            width: 100%;
            height: 100%;
        }
    </style>
</head>
<body>
<div id="canvas-container"></div>

<script type="importmap">
{
    "imports": {
        "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
        "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
    }
}
</script>

<script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
    import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
    import { STLLoader } from 'three/addons/loaders/STLLoader.js';

    const container = document.getElementById('canvas-container');

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    // Camera
    const camera = new THREE.PerspectiveCamera(
        60, container.clientWidth / container.clientHeight, 0.1, 1000
    );
    camera.position.set(3, 3, 3);
    camera.lookAt(0, 0, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, 10, 7);
    scene.add(directionalLight);

    const robotRoot = new THREE.Group();
    robotRoot.name = 'robot-root';
    scene.add(robotRoot);

    const gltfLoader = new GLTFLoader();
    const objLoader = new OBJLoader();
    const stlLoader = new STLLoader();

    function disposeMaterial(material) {
        if (Array.isArray(material)) {
            material.forEach(disposeMaterial);
            return;
        }
        if (material && typeof material.dispose === 'function') {
            material.dispose();
        }
    }

    function disposeObject(root) {
        root.traverse((obj) => {
            if (!obj.isMesh) {
                return;
            }
            if (obj.geometry) {
                obj.geometry.dispose();
            }
            disposeMaterial(obj.material);
        });
    }

    function makeMaterial(options = {}, fallbackColor = 0x4a90d9) {
        return new THREE.MeshStandardMaterial({
            color: options.color ?? fallbackColor,
            flatShading: options.flatShading !== false,
        });
    }

    function restyleObject(root, options = {}) {
        root.traverse((obj) => {
            if (!obj.isMesh) {
                return;
            }
            const fallbackColor = obj.material?.color?.getHex?.() ?? 0x4a90d9;
            obj.material = makeMaterial(options, fallbackColor);
        });
    }

    function normalizeObject(wrapper, content, options = {}) {
        content.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(content);
        if (box.isEmpty()) {
            return;
        }

        const center = box.getCenter(new THREE.Vector3());
        const offset = new THREE.Vector3();

        if (options.center !== false) {
            offset.x = -center.x;
            offset.z = -center.z;
        }

        if (options.baseOnGround !== false) {
            offset.y = -box.min.y;
        } else if (options.centerY === true) {
            offset.y = -center.y;
        }

        content.position.add(offset);
        wrapper.updateMatrixWorld(true);
    }

    function degreesToRadians(degrees) {
        return degrees * Math.PI / 180;
    }

    function applyTransform(object3d, transform = {}, rotationUnit = 'degrees') {
        const position = transform.position ?? [0, 0, 0];
        let rotation = transform.rotation ?? [0, 0, 0];
        const scale = transform.scale ?? [1, 1, 1];

        // Convert rotation from degrees to radians if needed
        if (rotationUnit.toLowerCase() === 'degrees') {
            rotation = [
                degreesToRadians(rotation[0] ?? 0),
                degreesToRadians(rotation[1] ?? 0),
                degreesToRadians(rotation[2] ?? 0)
            ];
        }

        object3d.position.set(position[0] ?? 0, position[1] ?? 0, position[2] ?? 0);
        object3d.rotation.set(rotation[0] ?? 0, rotation[1] ?? 0, rotation[2] ?? 0);

        if (Array.isArray(scale)) {
            object3d.scale.set(scale[0] ?? 1, scale[1] ?? 1, scale[2] ?? 1);
        } else {
            object3d.scale.setScalar(scale ?? 1);
        }
    }

    function removeObjectByName(name) {
        const existing = robotRoot.getObjectByName(name);
        if (!existing) {
            return;
        }
        robotRoot.remove(existing);
        disposeObject(existing);
    }

    function attachLoadedObject(name, content, options = {}) {
        removeObjectByName(name);
        restyleObject(content, options);

        const wrapper = new THREE.Group();
        wrapper.name = name;
        wrapper.add(content);
        normalizeObject(wrapper, content, options);
        const rotationUnit = options.rotation_unit ?? 'degrees';
        applyTransform(wrapper, options, rotationUnit);
        robotRoot.add(wrapper);
    }

    function loadModel(name, url, options = {}) {
        const normalizedUrl = String(url).split('?')[0].split('#')[0].toLowerCase();

        if (normalizedUrl.endsWith('.obj')) {
            objLoader.load(
                url,
                (content) => attachLoadedObject(name, content, options),
                undefined,
                (error) => console.error(`Failed to load OBJ ${name}:`, error),
            );
            return;
        }

        if (normalizedUrl.endsWith('.gltf') || normalizedUrl.endsWith('.glb')) {
            gltfLoader.load(
                url,
                (gltf) => attachLoadedObject(name, gltf.scene, options),
                undefined,
                (error) => console.error(`Failed to load GLTF ${name}:`, error),
            );
            return;
        }

        if (normalizedUrl.endsWith('.stl')) {
            stlLoader.load(
                url,
                (geometry) => {
                    const mesh = new THREE.Mesh(geometry, makeMaterial(options));
                    attachLoadedObject(name, mesh, options);
                },
                undefined,
                (error) => console.error(`Failed to load STL ${name}:`, error),
            );
            return;
        }

        console.error(`Unsupported model format for ${name}: ${url}`);
    }
    // Grid helper
    const grid = new THREE.GridHelper(10, 10, 0x444466, 0x333355);
    scene.add(grid);

    // Axes helper
    const axes = new THREE.AxesHelper(2);
    scene.add(axes);

    // Resize handling
    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }
    animate();

    // Expose API for Python calls via runJavaScript
    window.clearScene = function() {
        [...robotRoot.children].forEach((child) => {
            robotRoot.remove(child);
            disposeObject(child);
        });
    };

    window.addBox = function(x, y, z, w, h, d, color) {
        const geo = new THREE.BoxGeometry(w || 1, h || 1, d || 1);
        const mat = new THREE.MeshStandardMaterial({ color: color || 0x4a90d9 });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x || 0, y || 0, z || 0);
        robotRoot.add(mesh);
    };

    window.loadModel = function(name, url, options = {}) {
        loadModel(name, url, options);
    };

    window.setObjectTransform = function(name, transform = {}, rotationUnit = 'degrees') {
        const object3d = robotRoot.getObjectByName(name);
        if (!object3d) {
            console.warn(`Unknown object: ${name}`);
            return false;
        }
        applyTransform(object3d, {
            position: transform.position ?? [object3d.position.x, object3d.position.y, object3d.position.z],
            rotation: transform.rotation ?? [object3d.rotation.x, object3d.rotation.y, object3d.rotation.z],
            scale: transform.scale ?? [object3d.scale.x, object3d.scale.y, object3d.scale.z],
        }, rotationUnit);
        return true;
    };

    window.removeObject = function(name) {
        removeObjectByName(name);
    };

    window.loadGLTF = function(url) {
        loadModel('gltf-model', url, {});
    };

    window.loadSTL = function(url, color) {
        loadModel('stl-model', url, { color: color || 0x4a90d9 });
    };
</script>
</body>
</html>
"""


class ThreejsViewer(QWidget):
    def __init__(self, config=None):
        super().__init__()
        self.setMinimumSize(400, 300)
        self._view = None
        self._config = config or {}
        self._html_file = Path(tempfile.gettempdir()) / "threejs_viewer.html"
        self._project_root = Path(__file__).resolve().parents[3]
        self._is_ready = False
        self._pending_scripts = []

    def build(self):
        self._view = QWebEngineView()
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self._view.loadFinished.connect(self._on_load_finished)

        self._html_file.write_text(HTML, encoding="utf-8")
        self._view.load(QUrl.fromLocalFile(str(self._html_file)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def _on_load_finished(self, ok):
        self._is_ready = bool(ok)
        if not ok:
            return

        pending_scripts = list(self._pending_scripts)
        self._pending_scripts.clear()
        for script in pending_scripts:
            self._view.page().runJavaScript(script)

        object_sources = self._config.get("object_sources", [])
        if object_sources:
            self.load_objects(object_sources, clear_existing=True)

    def _resolve_source_url(self, source: str) -> str:
        source_path = Path(source)
        candidates = []

        if source_path.is_absolute():
            candidates.append(source_path)
        else:
            candidates.append(self._project_root / source_path)
            candidates.append(self._project_root / "src" / source_path)

        for candidate in candidates:
            if candidate.exists():
                return QUrl.fromLocalFile(str(candidate.resolve())).toString()

        return source

    @staticmethod
    def _vector3(value, default):
        if value is None:
            return list(default)
        if isinstance(value, (int, float)):
            return [value, value, value]
        return list(value)

    def run_js(self, script):
        """Execute arbitrary JavaScript in the viewer."""
        if not self._view:
            return
        if not self._is_ready:
            self._pending_scripts.append(script)
            return
        self._view.page().runJavaScript(script)

    def clear_scene(self):
        self.run_js("window.clearScene();")

    def load_object(
        self,
        name,
        source,
        position=None,
        rotation=None,
        scale=None,
        center=True,
        base_on_ground=True,
        color=None,
        flat_shading=True,
    ):
        options = {
            "position": self._vector3(position, (0, 0, 0)),
            "rotation": self._vector3(rotation, (0, 0, 0)),
            "scale": self._vector3(scale, (1, 1, 1)),
            "center": center,
            "baseOnGround": base_on_ground,
            "flatShading": flat_shading,
        }
        if color is not None:
            options["color"] = color

        source_url = self._resolve_source_url(source)
        self.run_js(
            f"window.loadModel({json.dumps(name)}, {json.dumps(source_url)}, {json.dumps(options)});"
        )

    def load_objects(self, objects, clear_existing=False):
        if clear_existing:
            self.clear_scene()

        for object_cfg in objects:
            name = object_cfg.get("name")
            source = object_cfg.get("source")
            if not name or not source:
                continue
            self.load_object(
                name=name,
                source=source,
                position=object_cfg.get("position"),
                rotation=object_cfg.get("rotation"),
                scale=object_cfg.get("scale"),
                center=object_cfg.get("center", True),
                base_on_ground=object_cfg.get(
                    "base_on_ground",
                    object_cfg.get("baseOnGround", True),
                ),
                color=object_cfg.get("color"),
                flat_shading=object_cfg.get("flat_shading", True),
            )

    def set_object_transform(self, name, position=None, rotation=None, scale=None):
        transform = {}
        if position is not None:
            transform["position"] = self._vector3(position, (0, 0, 0))
        if rotation is not None:
            transform["rotation"] = self._vector3(rotation, (0, 0, 0))
        if scale is not None:
            transform["scale"] = self._vector3(scale, (1, 1, 1))
        self.run_js(
            f"window.setObjectTransform({json.dumps(name)}, {json.dumps(transform)});"
        )

    def set_object_position(self, name, x, y, z):
        self.set_object_transform(name, position=[x, y, z])

    def set_object_rotation(self, name, rx, ry, rz):
        self.set_object_transform(name, rotation=[rx, ry, rz])

    def set_object_scale(self, name, sx, sy, sz):
        self.set_object_transform(name, scale=[sx, sy, sz])

    def remove_object(self, name):
        self.run_js(f"window.removeObject({json.dumps(name)});")

    def add_box(self, x=0, y=0, z=0, w=1, h=1, d=1, color=0x4a90d9):
        self.run_js(f"window.addBox({x},{y},{z},{w},{h},{d},{color});")

    def load_gltf(self, url):
        self.run_js(f"window.loadGLTF('{url}');")

    def load_stl(self, url, color=0x4a90d9):
        self.run_js(f"window.loadSTL('{url}', {color});")

    def update(self, data=None):
        """Rebuild scene from config data."""
        if data is None:
            return
        self._config = data
        self.load_objects(data.get("object_sources", []), clear_existing=True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ThreejsViewer()
    w.build()
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())
