#ifndef POINTCLOUD_VIEWER_H
#define POINTCLOUD_VIEWER_H

#include <QWidget>
#include <QVBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QSlider>
#include <QComboBox>
#include <QCheckBox>
#include <QVBoxLayout>
#include <vector>

#ifdef WITH_ROS2
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <rclcpp/rclcpp.hpp>
#include <thread>
#include <atomic>
#include <memory>
#endif

#if defined(WITH_PCL_VIS)
#include <pcl_conversions/pcl_conversions.h>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/visualization/pcl_visualizer.h>
#include <vtkRenderWindow.h>
#include <QVTKOpenGLNativeWidget.h>
#endif

class PointCloudViewer : public QWidget
{
    Q_OBJECT

public:
    explicit PointCloudViewer(QWidget *parent = nullptr, bool useMockData = false);
    ~PointCloudViewer();

#if defined(WITH_ROS2)
    // Start/stop a simple ROS2 subscription to a PointCloud2 topic
    void startRosSubscription(const std::string &topic);
    void stopRosSubscription();
#endif

public slots:
#ifdef WITH_ROS2
    void updatePointCloud(const sensor_msgs::msg::PointCloud2::SharedPtr msg);
#endif
    void clearPointCloud();
    void toggleMockData(bool enable);
    void onAnimationSpeedChanged(int value);
    void onPointSizeChanged(int value);
    void onColorModeChanged(int index);
    void onEnableGradientChanged(int state);

private:
    void setupRealUI();
    // layout container
    QVBoxLayout* layout_;
    
    // Controls
    QSlider* point_size_slider_;
    QSlider* animation_speed_slider_;
    QComboBox* color_mode_combo_;
    QCheckBox* gradient_checkbox_;
    QLabel* point_size_label_;
    QLabel* animation_speed_label_;
    
    // Settings
    float point_size_;
    float animation_speed_;
    int color_mode_;
    bool use_gradient_;
    // Point cloud data (if needed by real UI)
    std::vector<float> point_positions_;
    std::vector<float> point_colors_;
    
    
#if defined(WITH_PCL_VIS)
    QVTKOpenGLNativeWidget* vtk_widget_;
    pcl::visualization::PCLVisualizer::Ptr viewer_;
    bool cloud_added_;
    std::string cloud_id_;
#endif

#if defined(WITH_ROS2)
signals:
    void pointCloudMsgReceived(sensor_msgs::msg::PointCloud2::SharedPtr msg);

private:
    rclcpp::Node::SharedPtr ros_node_;
    rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr pc_sub_;
    std::thread ros_thread_;
    std::atomic_bool ros_running_{false};
#endif
};

#endif // POINTCLOUD_VIEWER_H
