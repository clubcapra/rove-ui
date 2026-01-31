#include "views/map_viewer.h"
#include <QAction>
#include <QIcon>
#include <QLabel>
#include <QDateTime>

MapViewer::MapViewer(QWidget *parent)
    : QWidget(parent)
    , layout_(new QVBoxLayout(this))
    , web_view_(new QWebEngineView(this))
    , toolbar_(new QToolBar(this))
    , map_type_combo_(new QComboBox(this))
    , current_lat_(45.5017)  // Default: Montreal
    , current_lon_(-73.5673)
    , current_zoom_(13)
    , current_map_type_(SATELLITE)
{
    // Setup toolbar
    toolbar_->setMovable(false);
    
    // Map type selector
    map_type_combo_->addItem("Satellite");
    map_type_combo_->addItem("Roadmap");
    map_type_combo_->addItem("Hybrid");
    map_type_combo_->addItem("Terrain");
    connect(map_type_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged), 
            this, &MapViewer::onMapTypeChanged);
    
    toolbar_->addWidget(new QLabel("Type de carte: "));
    toolbar_->addWidget(map_type_combo_);
    toolbar_->addSeparator();
    
    // Zoom controls
    QAction* zoom_in_action = toolbar_->addAction("Zoom +");
    QAction* zoom_out_action = toolbar_->addAction("Zoom -");
    connect(zoom_in_action, &QAction::triggered, this, &MapViewer::zoomIn);
    connect(zoom_out_action, &QAction::triggered, this, &MapViewer::zoomOut);
    
    // Layout
    layout_->addWidget(toolbar_);
    layout_->addWidget(web_view_);
    layout_->setContentsMargins(0, 0, 0, 0);
    setLayout(layout_);
    
    // Load initial map
    loadMap();
}

MapViewer::~MapViewer()
{
}

void MapViewer::setCenter(double latitude, double longitude, int zoom)
{
    current_lat_ = latitude;
    current_lon_ = longitude;
    current_zoom_ = zoom;
    loadMap();
}

void MapViewer::addMarker(double latitude, double longitude, const QString& title)
{
    QString js = QString(
        "var marker = L.marker([%1, %2]).addTo(map);"
        "marker.bindPopup('%3');"
    ).arg(latitude).arg(longitude).arg(title);
    
    web_view_->page()->runJavaScript(js);
}

void MapViewer::setMapType(MapType type)
{
    current_map_type_ = type;
    map_type_combo_->setCurrentIndex(static_cast<int>(type));
    loadMap();
}

void MapViewer::updateRobotPosition(double latitude, double longitude)
{
    QString js = QString(
        "if (window.robotMarker) {"
        "    map.removeLayer(window.robotMarker);"
        "}"
        "window.robotMarker = L.marker([%1, %2], {"
        "    icon: L.icon({"
        "        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',"
        "        iconSize: [25, 41],"
        "        iconAnchor: [12, 41]"
        "    })"
        "}).addTo(map);"
        "window.robotMarker.bindPopup('Robot Position');"
        "map.setView([%1, %2]);"
    ).arg(latitude).arg(longitude);
    
    web_view_->page()->runJavaScript(js);
}

void MapViewer::onMapTypeChanged(int index)
{
    current_map_type_ = static_cast<MapType>(index);
    loadMap();
}

void MapViewer::zoomIn()
{
    current_zoom_ = qMin(current_zoom_ + 1, 18);
    web_view_->page()->runJavaScript(QString("map.setZoom(%1);").arg(current_zoom_));
}

void MapViewer::zoomOut()
{
    current_zoom_ = qMax(current_zoom_ - 1, 1);
    web_view_->page()->runJavaScript(QString("map.setZoom(%1);").arg(current_zoom_));
}

void MapViewer::loadMap()
{
    QString html = generateMapHtml();
    web_view_->setHtml(html);
}

QString MapViewer::generateMapHtml()
{
    QString tile_layer;
    
    switch (current_map_type_) {
        case SATELLITE:
            tile_layer = "L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution: 'Tiles &copy; Esri'})";
            break;
        case ROADMAP:
            tile_layer = "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '&copy; OpenStreetMap contributors'})";
            break;
        case HYBRID:
            tile_layer = "L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution: 'Tiles &copy; Esri'})";
            break;
        case TERRAIN:
            tile_layer = "L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {attribution: 'Map data: &copy; OpenTopoMap'})";
            break;
    }
    
    QString html = QString(R"(
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body { margin: 0; padding: 0; }
        #map { position: absolute; top: 0; bottom: 0; width: 100%; }
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([%1, %2], %3);
        %4.addTo(map);
    </script>
</body>
</html>
    )").arg(current_lat_).arg(current_lon_).arg(current_zoom_).arg(tile_layer);
    
    return html;
}
