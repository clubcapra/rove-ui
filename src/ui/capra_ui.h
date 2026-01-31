#ifndef CAPRA_UI_H
#define CAPRA_UI_H

#include <QMainWindow>
#include <QTabWidget>
#include <QDockWidget>
#include <QTextEdit>
#include <QStatusBar>
#include <QMenuBar>
#include <QMenu>
#include <QAction>
#include "views/map_viewer.h"
#include "views/rtsp_viewer.h"
#include "views/pointcloud_viewer.h"
#include "core/config_manager.h"
#include "config_dialog.h"

#ifdef WITH_ROS2
#include "adapters/ros_node.h"
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#endif

QT_BEGIN_NAMESPACE
namespace Ui {
class CAPRA_UI;
}
QT_END_NAMESPACE

class CAPRA_UI : public QMainWindow
{
    Q_OBJECT

public:
    CAPRA_UI(QWidget *parent = nullptr);
    ~CAPRA_UI();

private slots:
#ifdef WITH_ROS2
    void onPointCloudReceived(const sensor_msgs::msg::PointCloud2::SharedPtr msg);
    void onPoseReceived(const geometry_msgs::msg::PoseStamped::SharedPtr msg);
#endif
    void onConfigChanged();
    void onOpenConfigDialog();

private:
    Ui::CAPRA_UI *ui;
    
#ifdef WITH_ROS2
    // ROS 2 Node
    RosNode* ros_node_;
#endif
    
    // Viewers (dynamic based on config)
    PointCloudViewer* pointcloud_viewer_;  // Disponible aussi en mode standalone (mock)
    MapViewer* map_viewer_;
    QList<RtspViewer*> rtsp_viewers_;
    QList<class LayoutPanel*> layout_panels_;
    
    // UI Components
    QTabWidget* tab_widget_;
    QDockWidget* log_dock_;
    QTextEdit* log_text_;
    
    void setupUI();
    void setupMenuBar();
    void setupConnections();
    void buildPanelsFromConfig();
    void applyConfiguration();
    void logMessage(const QString& message);
    
    // Helper pour créer des widgets à partir de la config
    QWidget* createWidgetFromPanel(const ConfigManager::PanelConfig& panel);
};
#endif // CAPRA_UI_H
