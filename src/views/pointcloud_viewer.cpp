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
{
    layout_ = new QVBoxLayout(this);
    layout_->setContentsMargins(0, 0, 0, 0);

        // Use an embedded Three.js WebGL viewer hosted inside QWebEngineView.
        web_view_ = new QWebEngineView(this);

        const QString html = R"(<html>
    <head>
        <meta charset='utf-8'>
        <meta http-equiv='Content-Security-Policy' content="default-src 'self' https: 'unsafe-inline' 'unsafe-eval'">
        <style>html,body{height:100%;margin:0;background:#111;color:#ddd}#gl{width:100%;height:100%}</style>
        <script src='https://unpkg.com/three@0.152.2/build/three.min.js'></script>
    </head>
    <body>
        <div id='gl'></div>
        <script>
            let scene = new THREE.Scene();
            let camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.01, 1000);
            camera.position.set(0,0,3);
            let renderer = new THREE.WebGLRenderer({antialias:true});
            renderer.setSize(window.innerWidth, window.innerHeight);
            document.getElementById('gl').appendChild(renderer.domElement);

            let pointsMesh = null;
            let pointMaterial = new THREE.PointsMaterial({size: 0.02, vertexColors: true});

            function buildFromBuffer(buffer, count, hasColor){
                const positions = new Float32Array(buffer, 0, count*3);
                let geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
                if(hasColor){
                    const colorOffset = count*3*4;
                    const colorsU8 = new Uint8Array(buffer, colorOffset, count*3);
                    const colors = new Float32Array(count*3);
                    for(let i=0;i<count*3;i++) colors[i] = colorsU8[i] / 255.0;
                    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
                    pointMaterial.vertexColors = true;
                } else {
                    pointMaterial.vertexColors = false;
                    pointMaterial.color = new THREE.Color(0xFFFFFF);
                }
                if(pointsMesh) scene.remove(pointsMesh);
                pointsMesh = new THREE.Points(geometry, pointMaterial);
                scene.add(pointsMesh);
            }

            function animate(){
                requestAnimationFrame(animate);
                renderer.render(scene, camera);
            }
            animate();

            window.receivePointCloud = function(base64, count, hasColor){
                try{
                    const binary_string = atob(base64);
                    const len = binary_string.length;
                    const bytes = new Uint8Array(len);
                    for(let i=0;i<len;i++) bytes[i] = binary_string.charCodeAt(i);
                    // We use an ArrayBuffer view of the bytes
                    const buf = bytes.buffer;
                    buildFromBuffer(buf, count, !!hasColor);
                }catch(e){
                    console.error('receivePointCloud error', e);
                }
            }

            window.setPointSize = function(s){ if(pointMaterial) pointMaterial.size = s; }

            window.onresize = function(){
                camera.aspect = window.innerWidth/window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            }
        </script>
    </body>
</html>)";

        web_view_->setHtml(html, QUrl("qrc:///"));
        connect(web_view_, &QWebEngineView::loadFinished, this, [this](bool ok){
                Q_UNUSED(ok)
                page_loaded_ = true;
        });
        layout_->addWidget(web_view_);
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

void PointCloudViewer::setupRealUI()
{
    // kept for API compatibility; currently we present the web stub instead
}

void PointCloudViewer::updatePointCloud(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
{
    if (!msg) return;

    // find offsets for x,y,z and color fields
    int x_off=-1,y_off=-1,z_off=-1;
    int rgb_off=-1; // packed float32 rgb
    int r_off=-1,g_off=-1,b_off=-1;
    for (const auto &f : msg->fields) {
        if (f.name == "x") x_off = f.offset;
        else if (f.name == "y") y_off = f.offset;
        else if (f.name == "z") z_off = f.offset;
        else if (f.name == "rgb") rgb_off = f.offset;
        else if (f.name == "r") r_off = f.offset;
        else if (f.name == "g") g_off = f.offset;
        else if (f.name == "b") b_off = f.offset;
    }

    const size_t count = msg->width * msg->height;
    if (count == 0) return;

    const size_t posBytes = count * 3 * sizeof(float);
    const bool hasColor = (rgb_off>=0) || (r_off>=0 && g_off>=0 && b_off>=0);
    const size_t colorBytes = hasColor ? count * 3 : 0;

    QByteArray buffer;
    buffer.resize(posBytes + colorBytes);

    // fill positions
    for (size_t i=0;i<count;i++){
        size_t base = i * msg->point_step;
        float x=0,y=0,z=0;
        if (x_off>=0) memcpy(&x, &msg->data[base + x_off], sizeof(float));
        if (y_off>=0) memcpy(&y, &msg->data[base + y_off], sizeof(float));
        if (z_off>=0) memcpy(&z, &msg->data[base + z_off], sizeof(float));
        // write into buffer as float32 little-endian
        size_t pindex = i*3;
        float *posPtr = reinterpret_cast<float*>(buffer.data());
        posPtr[pindex+0] = x;
        posPtr[pindex+1] = y;
        posPtr[pindex+2] = z;
    }

    // fill colors (uint8 r,g,b)
    if (hasColor){
        const size_t colorOffset = posBytes;
        for (size_t i=0;i<count;i++){
            size_t base = i * msg->point_step;
            unsigned char r=255,g=255,b=255;
            if (rgb_off>=0) {
                // unpack packed float rgb (PCL stores as float)
                uint32_t packed=0;
                memcpy(&packed, &msg->data[base + rgb_off], sizeof(uint32_t));
                unsigned char* p = reinterpret_cast<unsigned char*>(&packed);
                // often B G R order in packed float - try to map
                b = p[0]; g = p[1]; r = p[2];
            } else {
                if (r_off>=0) r = msg->data[base + r_off];
                if (g_off>=0) g = msg->data[base + g_off];
                if (b_off>=0) b = msg->data[base + b_off];
            }
            buffer[colorOffset + i*3 + 0] = static_cast<char>(r);
            buffer[colorOffset + i*3 + 1] = static_cast<char>(g);
            buffer[colorOffset + i*3 + 2] = static_cast<char>(b);
        }
    }

    // base64 encode and send to page
    const QByteArray b64 = buffer.toBase64();

    // Build JS call
    const QString js = QString("window.receivePointCloud('%1', %2, %3);")
        .arg(QString::fromLatin1(b64))
        .arg((int)count)
        .arg(hasColor ? 1 : 0);

    // If page not ready yet, ignore (or could queue)
    if (!page_loaded_) return;

    web_view_->page()->runJavaScript(js);
}

void PointCloudViewer::clearPointCloud()
{
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

