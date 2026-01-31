#include "views/pointcloud_viewer.h"
#include <QLabel>
#include <cmath>

PointCloudViewer::PointCloudViewer(QWidget *parent, bool /*useMockData*/)
    : QWidget(parent)
    , layout_(nullptr)
    , point_size_slider_(nullptr)
    , animation_speed_slider_(nullptr)
    , color_mode_combo_(nullptr)
    , gradient_checkbox_(nullptr)
    , point_size_label_(nullptr)
    , animation_speed_label_(nullptr)
    , point_size_(2.0f)
    , animation_speed_(1.0f)
    , color_mode_(0)
    , use_gradient_(true)
#if defined(WITH_PCL_VIS)
    , vtk_widget_(nullptr)
    , viewer_(nullptr)
    , cloud_added_(false)
    , cloud_id_("cloud")
#endif
{
    layout_ = new QVBoxLayout(this);
    layout_->setContentsMargins(0, 0, 0, 0);

#if defined(WITH_PCL_VIS)
    setupRealUI();
#else
    QLabel* info = new QLabel("PCL/VTK visualization disabled", this);
    info->setAlignment(Qt::AlignCenter);
    layout_->addWidget(info);
#endif
}

PointCloudViewer::~PointCloudViewer()
{
#if defined(WITH_ROS2)
    stopRosSubscription();
#endif
}

#if defined(WITH_ROS2)
void PointCloudViewer::startRosSubscription(const std::string &topic)
{
    if (ros_running_.load()) return;

    if (!rclcpp::ok()) {
        int argc = 0;
        char **argv = nullptr;
        rclcpp::init(argc, argv);
    }

    ros_node_ = std::make_shared<rclcpp::Node>("capraui_pointcloud_listener");

    pc_sub_ = ros_node_->create_subscription<sensor_msgs::msg::PointCloud2>(
        topic, rclcpp::SystemDefaultsQoS(),
        [this](sensor_msgs::msg::PointCloud2::SharedPtr msg) {
            emit pointCloudMsgReceived(msg);
        }
    );

    connect(this, &PointCloudViewer::pointCloudMsgReceived,
            this, &PointCloudViewer::updatePointCloud,
            Qt::QueuedConnection);

    ros_running_.store(true);
    ros_thread_ = std::thread([this]() {
        rclcpp::spin(ros_node_);
    });
}

void PointCloudViewer::stopRosSubscription()
{
    if (!ros_running_.load()) return;

    // Reset subscription and node, then shutdown rclcpp and join thread
    pc_sub_.reset();
    if (ros_node_) {
        ros_node_.reset();
    }

    // Shutdown and join
    if (rclcpp::ok()) {
        rclcpp::shutdown();
    }
    if (ros_thread_.joinable()) ros_thread_.join();

    ros_running_.store(false);
}
#endif

#if defined(WITH_PCL_VIS)
void PointCloudViewer::setupRealUI()
{
    vtk_widget_ = new QVTKOpenGLNativeWidget(this);
    layout_->addWidget(vtk_widget_);

    viewer_.reset(new pcl::visualization::PCLVisualizer("Point Cloud Viewer", false));
    viewer_->setBackgroundColor(0.1, 0.1, 0.1);
    viewer_->addCoordinateSystem(1.0);
    viewer_->initCameraParameters();

    vtk_widget_->setRenderWindow(viewer_->getRenderWindow());
    viewer_->setupInteractor(vtk_widget_->interactor(), vtk_widget_->renderWindow());

    QLabel* info = new QLabel("En attente de données ROS 2...", this);
    info->setAlignment(Qt::AlignCenter);
    info->setStyleSheet("QLabel { color: #00ff00; background-color: rgba(0,0,0,100); padding: 5px; }");
    layout_->addWidget(info);
}

void PointCloudViewer::updatePointCloud(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
{
    if (!viewer_) return;

    pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    pcl::fromROSMsg(*msg, *cloud);

    if (cloud_added_) {
        viewer_->updatePointCloud(cloud, cloud_id_);
    } else {
        viewer_->addPointCloud(cloud, cloud_id_);
        cloud_added_ = true;
    }

    viewer_->spinOnce();
    vtk_widget_->update();
}
#elif defined(WITH_ROS2)
void PointCloudViewer::updatePointCloud(const sensor_msgs::msg::PointCloud2::SharedPtr /*msg*/)
{
    // PCL visualization disabled; no-op
}
#endif

void PointCloudViewer::clearPointCloud()
{
#if defined(WITH_PCL_VIS)
    if (viewer_ && cloud_added_) {
        viewer_->removePointCloud(cloud_id_);
        cloud_added_ = false;
        viewer_->spinOnce();
        vtk_widget_->update();
    }
#endif

    point_positions_.clear();
    point_colors_.clear();
}

void PointCloudViewer::toggleMockData(bool /*enable*/)
{
    // Mock data removed; no-op
}

void PointCloudViewer::onPointSizeChanged(int value)
{
    point_size_ = value / 10.0f;
    if (point_size_label_) {
        point_size_label_->setText(QString("Taille des particules: %1").arg(point_size_, 0, 'f', 1));
    }
#if defined(WITH_PCL_VIS)
    if (viewer_) {
        viewer_->setPointCloudRenderingProperties(pcl::visualization::PCL_VISUALIZER_POINT_SIZE, static_cast<double>(point_size_), cloud_id_);
    }
#endif
}

void PointCloudViewer::onColorModeChanged(int index)
{
    color_mode_ = index;
}

void PointCloudViewer::onAnimationSpeedChanged(int value)
{
    animation_speed_ = value / 10.0f;
    if (animation_speed_label_) {
        animation_speed_label_->setText(QString("Vitesse animation: %1x").arg(animation_speed_, 0, 'f', 1));
    }
}

void PointCloudViewer::onEnableGradientChanged(int state)
{
    use_gradient_ = (state == Qt::Checked);
}
