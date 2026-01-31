#ifndef ROS_NODE_H
#define ROS_NODE_H

#include <QObject>
#include <QTimer>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>

class RosNode : public QObject
{
    Q_OBJECT

public:
    explicit RosNode(QObject *parent = nullptr);
    ~RosNode();

    // Initialize ROS 2 node
    void init(int argc, char** argv);
    
    // Subscribe to topics
    void subscribeToPointCloud(const std::string& topic);
    void subscribeToImage(const std::string& topic);
    void subscribeToPose(const std::string& topic);

signals:
    // Signals to emit when new data arrives
    void pointCloudReceived(const sensor_msgs::msg::PointCloud2::SharedPtr msg);
    void imageReceived(const sensor_msgs::msg::Image::SharedPtr msg);
    void poseReceived(const geometry_msgs::msg::PoseStamped::SharedPtr msg);

private slots:
    void spinOnce();

private:
    std::shared_ptr<rclcpp::Node> node_;
    rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr pointcloud_sub_;
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
    rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr pose_sub_;
    
    QTimer* spin_timer_;
    
    // Callback functions
    void pointCloudCallback(const sensor_msgs::msg::PointCloud2::SharedPtr msg);
    void imageCallback(const sensor_msgs::msg::Image::SharedPtr msg);
    void poseCallback(const geometry_msgs::msg::PoseStamped::SharedPtr msg);
};

#endif // ROS_NODE_H
