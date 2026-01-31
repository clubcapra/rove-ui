#include "adapters/ros_node.h"

RosNode::RosNode(QObject *parent)
    : QObject(parent)
    , spin_timer_(new QTimer(this))
{
    // Connect timer to spin ROS
    connect(spin_timer_, &QTimer::timeout, this, &RosNode::spinOnce);
}

RosNode::~RosNode()
{
    if (rclcpp::ok()) {
        rclcpp::shutdown();
    }
}

void RosNode::init(int argc, char** argv)
{
    // Initialize ROS 2
    rclcpp::init(argc, argv);
    
    // Create node
    node_ = std::make_shared<rclcpp::Node>("capra_ui_node");
    
    // Start spinning at 30 Hz
    spin_timer_->start(33); // ~30 Hz
}

void RosNode::subscribeToPointCloud(const std::string& topic)
{
    pointcloud_sub_ = node_->create_subscription<sensor_msgs::msg::PointCloud2>(
        topic, 
        10,
        std::bind(&RosNode::pointCloudCallback, this, std::placeholders::_1)
    );
}

void RosNode::subscribeToImage(const std::string& topic)
{
    image_sub_ = node_->create_subscription<sensor_msgs::msg::Image>(
        topic,
        10,
        std::bind(&RosNode::imageCallback, this, std::placeholders::_1)
    );
}

void RosNode::subscribeToPose(const std::string& topic)
{
    pose_sub_ = node_->create_subscription<geometry_msgs::msg::PoseStamped>(
        topic,
        10,
        std::bind(&RosNode::poseCallback, this, std::placeholders::_1)
    );
}

void RosNode::spinOnce()
{
    if (rclcpp::ok()) {
        rclcpp::spin_some(node_);
    }
}

void RosNode::pointCloudCallback(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
{
    emit pointCloudReceived(msg);
}

void RosNode::imageCallback(const sensor_msgs::msg::Image::SharedPtr msg)
{
    emit imageReceived(msg);
}

void RosNode::poseCallback(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
{
    emit poseReceived(msg);
}
