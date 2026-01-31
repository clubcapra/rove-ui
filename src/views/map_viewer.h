#ifndef MAP_VIEWER_H
#define MAP_VIEWER_H

#include <QWidget>
#include <QWebEngineView>
#include <QVBoxLayout>
#include <QComboBox>
#include <QToolBar>
#include <QAction>

class MapViewer : public QWidget
{
    Q_OBJECT

public:
    explicit MapViewer(QWidget *parent = nullptr);
    ~MapViewer();

    // Set map center coordinates
    void setCenter(double latitude, double longitude, int zoom = 13);
    
    // Add a marker on the map
    void addMarker(double latitude, double longitude, const QString& title = "");
    
    // Set map type
    enum MapType {
        SATELLITE,
        ROADMAP,
        HYBRID,
        TERRAIN
    };
    
    void setMapType(MapType type);

public slots:
    void updateRobotPosition(double latitude, double longitude);

private slots:
    void onMapTypeChanged(int index);
    void zoomIn();
    void zoomOut();

private:
    QVBoxLayout* layout_;
    QWebEngineView* web_view_;
    QToolBar* toolbar_;
    QComboBox* map_type_combo_;
    
    double current_lat_;
    double current_lon_;
    int current_zoom_;
    MapType current_map_type_;
    
    void loadMap();
    QString generateMapHtml();
};

#endif // MAP_VIEWER_H
