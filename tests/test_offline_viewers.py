import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse

from src.views.components.offline_assets import local_viewer_imports


class OfflineViewerTests(unittest.TestCase):
    def test_templates_resolve_all_modules_without_network(self):
        html_dir = Path(__file__).resolve().parents[1] / "src/views/components/html"
        for name in ["urdfViewer.html", "threejsViewer.html"]:
            html = local_viewer_imports((html_dir / name).read_text())
            imports = json.loads(re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1))["imports"]
            for specifier, url in imports.items():
                self.assertTrue(url.startswith("file:///"))
                path = Path(unquote(urlparse(url).path))
                self.assertTrue(path.exists(), path)
            for spec in re.findall(r"from ['\"]([^'\"]+)['\"]", html):
                path = imports.get(spec) or imports["three/addons/"] + spec.removeprefix("three/addons/")
                self.assertTrue(Path(unquote(urlparse(path).path)).is_file())

        vendor = html_dir / "vendor/three"
        for path in vendor.rglob("*.js"):
            code = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
            for spec in re.findall(r"import\s+[^;]*?from\s*['\"]([^'\"]+)['\"]", code):
                if spec.startswith("."):
                    self.assertTrue((path.parent / spec).resolve().is_file(), (path, spec))
                else:
                    self.assertEqual(spec, "three")


if __name__ == "__main__":
    unittest.main()
