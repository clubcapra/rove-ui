#include "ui/capra_ui.h"
#include "ui_capra_ui.h"
#include "views/layout_panel.h"
#include "views/web_page.h"
#include <QTimer>
#include <QVBoxLayout>
#include <QMessageBox>
#include <QDateTime>

CAPRA_UI::CAPRA_UI(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::CAPRA_UI)
#ifdef WITH_ROS2
    , ros_node_(new RosNode(this))
#endif
    , pointcloud_viewer_(nullptr)
    , map_viewer_(nullptr)
    , tab_widget_(new QTabWidget(this))
    , log_dock_(new QDockWidget("Logs", this))
    , log_text_(new QTextEdit(this))
{
    ui->setupUi(this);
    
#ifdef WITH_ROS2
    setWindowTitle("CAPRA UI - Interface de Contrôle Robot (avec ROS 2)");
#else
    setWindowTitle("CAPRA UI - Interface de Contrôle Robot (Mode Standalone)");
#endif
    resize(1280, 800);
    
    setupUI();
    setupMenuBar();
    setupConnections();
    
    // Load configuration and build UI
    applyConfiguration();
    
    logMessage("Application démarrée");
#ifdef WITH_ROS2
    logMessage("Mode: ROS 2 activé");
#else
    logMessage("Mode: Standalone (ROS 2 désactivé)");
#endif
    logMessage("Configuration: " + ConfigManager::instance().getConfigFilePath());
}

CAPRA_UI::~CAPRA_UI()
{
    delete ui;
}

void CAPRA_UI::setupUI()
{
    setCentralWidget(tab_widget_);
    
    // Setup log dock
    log_text_->setReadOnly(true);
    log_text_->setMaximumHeight(150);
    log_dock_->setWidget(log_text_);
    addDockWidget(Qt::BottomDockWidgetArea, log_dock_);
    
    // Status bar
    statusBar()->showMessage("Prêt");
}

void CAPRA_UI::setupMenuBar()
{
    // File menu
    QMenu* file_menu = menuBar()->addMenu("&Fichier");
    
    QAction* config_action = file_menu->addAction("&Configuration...");
    config_action->setShortcut(QKeySequence::Preferences);
    connect(config_action, &QAction::triggered, this, &CAPRA_UI::onOpenConfigDialog);
    
    file_menu->addSeparator();
    
    QAction* exit_action = file_menu->addAction("&Quitter");
    exit_action->setShortcut(QKeySequence::Quit);
    connect(exit_action, &QAction::triggered, this, &QMainWindow::close);
    
#ifdef WITH_ROS2
    // ROS menu
    QMenu* ros_menu = menuBar()->addMenu("&ROS");
    
    QAction* subscribe_pointcloud = ros_menu->addAction("S'abonner - Nuages de Points");
    connect(subscribe_pointcloud, &QAction::triggered, this, [this]() {
        QString topic = ConfigManager::instance().getPointCloudTopic();
        ros_node_->subscribeToPointCloud(topic.toStdString());
        logMessage("Abonné au topic: " + topic);
    });
    
    QAction* subscribe_pose = ros_menu->addAction("S'abonner - Position Robot");
    connect(subscribe_pose, &QAction::triggered, this, [this]() {
        QString topic = ConfigManager::instance().getPoseTopic();
        ros_node_->subscribeToPose(topic.toStdString());
        logMessage("Abonné au topic: " + topic);
    });
#endif
    
    // View menu
    QMenu* view_menu = menuBar()->addMenu("&Vue");
    
    QAction* toggle_log = view_menu->addAction("Afficher/Masquer Logs");
    connect(toggle_log, &QAction::triggered, this, [this]() {
        log_dock_->setVisible(!log_dock_->isVisible());
    });
    
    // Help menu
    QMenu* help_menu = menuBar()->addMenu("&Aide");
    
    QAction* about_action = help_menu->addAction("À &propos");
    connect(about_action, &QAction::triggered, this, [this]() {
        QMessageBox::about(this, "À propos de CAPRA UI",
            "CAPRA UI v0.1\n\n"
            "Interface de contrôle et visualisation pour robot ROS 2\n\n"
            "Fonctionnalités:\n"
            "- Visualisation de nuages de points (PCL)\n"
            "- Carte satellite interactive\n"
            "- Flux vidéo RTSP\n"
            "- Intégration ROS 2");
    });
}

void CAPRA_UI::setupConnections()
{
#ifdef WITH_ROS2
    // Connect ROS signals to viewer slots
    connect(ros_node_, &RosNode::pointCloudReceived,
            this, &CAPRA_UI::onPointCloudReceived);
    
    connect(ros_node_, &RosNode::poseReceived,
            this, &CAPRA_UI::onPoseReceived);
#endif
    
    // Connect config manager signals
    connect(&ConfigManager::instance(), &ConfigManager::configChanged,
            this, &CAPRA_UI::onConfigChanged);
}

QWidget* CAPRA_UI::createWidgetFromPanel(const ConfigManager::PanelConfig& panel)
{
    ConfigManager& config = ConfigManager::instance();
    QList<ConfigManager::RtspConfig> rtsp_streams = config.getRtspStreams();
    
    if (panel.type == "layout") {
        // Créer un layout panel
        LayoutPanel* layout_panel = new LayoutPanel(this);
        layout_panel->configureLayout(panel);
        layout_panels_.append(layout_panel);
        
        // Créer récursivement les widgets enfants
        int child_index = 0;
        for (const auto& child_panel : panel.children) {
            if (!child_panel.enabled) continue;
            
            QWidget* child_widget = createWidgetFromPanel(child_panel);
            if (child_widget) {
                if (panel.layout_type == "grid") {
                    int row = child_index / panel.columns;
                    int col = child_index % panel.columns;
                    layout_panel->addWidget(child_widget, row, col);
                } else {
                    layout_panel->addWidget(child_widget);
                }
                child_index++;
            }
        }
        
        logMessage(QString("Layout '%1' créé avec %2 enfants (%3)")
                   .arg(panel.title)
                   .arg(child_index)
                   .arg(panel.layout_type));
        return layout_panel;
        
    } else if (panel.type == "pointcloud") {
        bool use_mock = panel.properties.value("mock_mode", false).toBool();
        
#ifdef WITH_ROS2
        pointcloud_viewer_ = new PointCloudViewer(this, use_mock);
        if (use_mock) {
            logMessage("Nuage de points créé en mode MOCK");
        } else {
            logMessage("Nuage de points créé en mode ROS 2");
        }
        return pointcloud_viewer_;
#else
        if (use_mock) {
            pointcloud_viewer_ = new PointCloudViewer(this, true);
            logMessage("Nuage de points créé en mode MOCK (standalone)");
            return pointcloud_viewer_;
        } else {
            logMessage("Type 'pointcloud' sans mock_mode ignoré (ROS 2 non disponible)");
            return nullptr;
        }
#endif
        
    } else if (panel.type == "map") {
        map_viewer_ = new MapViewer(this);
        
        map_viewer_->setCenter(
            config.getMapLatitude(),
            config.getMapLongitude(),
            config.getMapZoom()
        );
        
        QString map_type = config.getMapType();
        if (map_type == "satellite") {
            map_viewer_->setMapType(MapViewer::SATELLITE);
        } else if (map_type == "roadmap") {
            map_viewer_->setMapType(MapViewer::ROADMAP);
        } else if (map_type == "hybrid") {
            map_viewer_->setMapType(MapViewer::HYBRID);
        } else if (map_type == "terrain") {
            map_viewer_->setMapType(MapViewer::TERRAIN);
        }
        
        return map_viewer_;
        
    } else if (panel.type == "rtsp") {
        int stream_index = panel.properties.value("stream_index", 0).toInt();
        
        if (stream_index < rtsp_streams.size()) {
            RtspViewer* rtsp_viewer = new RtspViewer(this);
            rtsp_viewers_.append(rtsp_viewer);
            
            if (config.getAutoConnect() && rtsp_streams[stream_index].enabled) {
                rtsp_viewer->connectToStream(rtsp_streams[stream_index].url);
            }
            
            return rtsp_viewer;
        }
    } else if (panel.type == "webview" || panel.type == "webpage") {
        // Web view panel — if this is a camera (json property "camera": true)
        // create a WebPage that can auto-supply auth and auto-fetch elements.
        bool is_camera = panel.properties.value("camera", false).toBool();
        QString url = panel.properties.value("url", "").toString();
        QString elementId = panel.properties.value("element_id", "").toString();
        QString username = panel.properties.value("username", "").toString();
        QString password = panel.properties.value("password", "").toString();

        // If panel doesn't specify credentials, fall back to global config
        if (username.isEmpty()) username = ConfigManager::instance().getCameraUsername();
        if (password.isEmpty()) password = ConfigManager::instance().getCameraPassword();

        WebPage* page = nullptr;
        if (is_camera) {
            // Specialized camera page removed; use generic WebPage instead
            page = new WebPage(this);
        } else {
            page = new WebPage(this);
        }

        if (!url.isEmpty()) {
            page->setUrl(url);
        }

        // Log results when retrieved
        connect(page, &WebPage::elementHtmlRetrieved, this, [this](const QString& id, const QString& html){
            if (html.isEmpty()) {
                logMessage(QString("Element '%1' introuvable ou vide").arg(id));
            } else {
                logMessage(QString("HTML récupéré pour '%1' (len=%2)").arg(id).arg(html.size()));
            }
        });

        connect(page, &WebPage::canvasDataUrlRetrieved, this, [this](const QString& id, const QString& dataUrl){
            if (dataUrl.isEmpty()) {
                logMessage(QString("Canvas '%1' introuvable ou conversion échouée").arg(id));
            } else {
                logMessage(QString("Canvas data URL récupérée pour '%1' (len=%2)").arg(id).arg(dataUrl.size()));
            }
        });

        return page;
    }
    
    return nullptr;
}

void CAPRA_UI::buildPanelsFromConfig()
{
    // Clear existing tabs
    while (tab_widget_->count() > 0) {
        tab_widget_->removeTab(0);
    }
    
    // Clean up old viewers
    if (pointcloud_viewer_) {
        pointcloud_viewer_->deleteLater();
        pointcloud_viewer_ = nullptr;
    }
    if (map_viewer_) {
        map_viewer_->deleteLater();
        map_viewer_ = nullptr;
    }
    for (RtspViewer* viewer : rtsp_viewers_) {
        viewer->deleteLater();
    }
    rtsp_viewers_.clear();
    
    for (LayoutPanel* layout : layout_panels_) {
        layout->deleteLater();
    }
    layout_panels_.clear();
    
    // Build panels from config
    ConfigManager& config = ConfigManager::instance();
    QList<ConfigManager::PanelConfig> panels = config.getPanels();
    
    for (const auto& panel : panels) {
        if (!panel.enabled) continue;
        
        QWidget* widget = createWidgetFromPanel(panel);
        if (widget) {
            tab_widget_->addTab(widget, panel.title);
        }
    }
    
    logMessage(QString("Interface reconstruite avec %1 panneaux").arg(tab_widget_->count()));
}

void CAPRA_UI::applyConfiguration()
{
    buildPanelsFromConfig();
    
#ifdef WITH_ROS2
    // Auto-subscribe to ROS topics if enabled
    ConfigManager& config = ConfigManager::instance();
    if (config.getAutoConnect()) {
        ros_node_->subscribeToPointCloud(config.getPointCloudTopic().toStdString());
        ros_node_->subscribeToPose(config.getPoseTopic().toStdString());
        logMessage("Auto-connexion aux topics ROS activée");
    }
#endif
}

#ifdef WITH_ROS2
void CAPRA_UI::onPointCloudReceived(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
{
    if (pointcloud_viewer_) {
        pointcloud_viewer_->updatePointCloud(msg);
        statusBar()->showMessage("Nuage de points mis à jour", 2000);
    }
}

void CAPRA_UI::onPoseReceived(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
{
    if (map_viewer_) {
        // Assuming pose contains GPS coordinates (latitude/longitude)
        // You may need to convert from pose to GPS coordinates depending on your setup
        double lat = msg->pose.position.x;  // Adjust according to your coordinate system
        double lon = msg->pose.position.y;  // Adjust according to your coordinate system
        
        map_viewer_->updateRobotPosition(lat, lon);
    }
    
    QString pose_msg = QString("Position: [%1, %2, %3]")
        .arg(msg->pose.position.x, 0, 'f', 2)
        .arg(msg->pose.position.y, 0, 'f', 2)
        .arg(msg->pose.position.z, 0, 'f', 2);
    
    statusBar()->showMessage(pose_msg, 2000);
    logMessage(pose_msg);
}
#endif

void CAPRA_UI::onConfigChanged()
{
    logMessage("Configuration modifiée, rechargement...");
    applyConfiguration();
}

void CAPRA_UI::onOpenConfigDialog()
{
    ConfigDialog dialog(this);
    if (dialog.exec() == QDialog::Accepted) {
        logMessage("Configuration sauvegardée");
        onConfigChanged();
    }
}

void CAPRA_UI::logMessage(const QString& message)
{
    QString timestamp = QDateTime::currentDateTime().toString("hh:mm:ss");
    log_text_->append(QString("[%1] %2").arg(timestamp, message));
}
