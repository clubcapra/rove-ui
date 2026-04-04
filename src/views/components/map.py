import os
import sys
from pathlib import Path

# Qt chooses a platform plugin (wayland/xcb/...) when the QApplication is created.
# If Wayland isn't available (common over SSH/X11), force XCB to avoid:
# "Failed to create wl_display" / "Could not load the Qt platform plugin 'wayland'".
if sys.platform.startswith("linux"):
    qt_qpa_platform = os.environ.get("QT_QPA_PLATFORM")
    if not qt_qpa_platform:
        has_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        has_x11 = bool(os.environ.get("DISPLAY"))
        if not has_wayland and has_x11:
            os.environ["QT_QPA_PLATFORM"] = "xcb"

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Carte avec tracé</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    />
    <script
        src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">
    </script>

    <style>
        html, body, #map {
            height: 100%;
            margin: 0;
            padding: 0;
        }
    </style>
</head>
<body>
<div id="map"></div>

<script>
    const map = L.map('map').setView([48.8566, 2.3522], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const positions = [
        [48.8566, 2.3522],
        [48.8572, 2.3540],
        [48.8580, 2.3560],
        [48.8590, 2.3585]
    ];

    // Marqueurs
    positions.forEach((pos, index) => {
        L.marker(pos).addTo(map).bindPopup("Point " + (index + 1));
    });

    // Tracé
    const line = L.polyline(positions, {
        weight: 4
    }).addTo(map);

    map.fitBounds(line.getBounds(), { padding: [20, 20] });
</script>
</body>
</html>
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Carte Qt6 + Leaflet")

        self.view = QWebEngineView()
        # Needed when loading a local `file://` HTML that references remote Leaflet/OSM URLs.
        # Without this, Leaflet doesn't load and JS errors with: "ReferenceError: L is not defined".
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.setCentralWidget(self.view)

        html_file = Path("map.html").resolve()
        html_file.write_text(HTML, encoding="utf-8")

        self.view.load(QUrl.fromLocalFile(str(html_file)))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    sys.exit(app.exec())