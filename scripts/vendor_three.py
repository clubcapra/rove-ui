"""Refresh the pinned offline Three.js modules (run on an internet connection)."""
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / "src/views/components/html/vendor/three"
FILES = (
    "build/three.module.js", "examples/jsm/controls/OrbitControls.js",
    "examples/jsm/loaders/GLTFLoader.js", "examples/jsm/loaders/OBJLoader.js",
    "examples/jsm/loaders/STLLoader.js", "examples/jsm/utils/BufferGeometryUtils.js",
    "LICENSE",
)

if __name__ == "__main__":
    for name in FILES:
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(f"https://unpkg.com/three@0.160.0/{name}", timeout=30) as response:
            target.write_bytes(response.read())
        print(name)
