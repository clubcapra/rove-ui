#include "views/rtsp_viewer.h"
#include <QPixmap>
#include <QDebug>

RtspViewer::RtspViewer(QWidget *parent)
    : QWidget(parent)
    , main_layout_(new QVBoxLayout(this))
    , control_layout_(new QHBoxLayout())
    , settings_layout_(new QHBoxLayout())
    , video_label_(new QLabel(this))
    , url_input_(new QLineEdit(this))
    , connect_button_(new QPushButton("Connecter", this))
    , disconnect_button_(new QPushButton("Déconnecter", this))
    , frame_timer_(new QTimer(this))
    , quality_slider_(new QSlider(Qt::Horizontal, this))
    , quality_label_(new QLabel("Qualité: 50%", this))
    , reduce_resolution_checkbox_(new QCheckBox("Réduire Résolution", this))
    , skip_frames_label_(new QLabel("Skip: 3", this))
    , skip_frames_slider_(new QSlider(Qt::Horizontal, this))
    , protocol_combo_(new QComboBox(this))
    , protocol_label_(new QLabel("Protocole:", this))
    , capture_(nullptr)
    , is_connected_(false)
    , jpeg_quality_(40)
    , reduce_resolution_(true)
    , frame_skip_count_(3)
    , protocol_type_("tcp")
{
    // Setup video label
    video_label_->setMinimumSize(640, 480);
    video_label_->setAlignment(Qt::AlignCenter);
    video_label_->setStyleSheet("QLabel { background-color: black; color: white; }");
    video_label_->setText("Aucun flux vidéo");
    video_label_->setScaledContents(true);
    
    // Setup URL input
    url_input_->setPlaceholderText("rtsp://admin:123456@ip:port/stream");
    url_input_->setText("rtsp://admin:123456@192.168.168.22:554/stream");
    
    // Setup buttons
    disconnect_button_->setEnabled(false);
    
    // Control layout
    control_layout_->addWidget(new QLabel("URL RTSP:"));
    control_layout_->addWidget(url_input_);
    control_layout_->addWidget(connect_button_);
    control_layout_->addWidget(disconnect_button_);
    
    // Setup latency controls
    setupLatencyControls();
    
    // Main layout
    main_layout_->addWidget(video_label_);
    main_layout_->addLayout(control_layout_);
    main_layout_->addLayout(settings_layout_);
    setLayout(main_layout_);
    
    // Connect signals
    connect(connect_button_, &QPushButton::clicked, this, &RtspViewer::onConnectClicked);
    connect(disconnect_button_, &QPushButton::clicked, this, &RtspViewer::onDisconnectClicked);
    connect(frame_timer_, &QTimer::timeout, this, &RtspViewer::updateFrame);
}

RtspViewer::~RtspViewer()
{
    disconnectStream();
}

void RtspViewer::connectToStream(const QString& url)
{
    // Disconnect if already connected
    if (is_connected_) {
        disconnectStream();
    }
    
    // Construire l'URL avec le protocole sélectionné
    std::string stream_url = url.toStdString();
    
    // Afficher le protocole choisi
    qDebug() << "[RTSP] Protocole sélectionné:" << protocol_type_;
    qDebug() << "[RTSP] URL originale:" << QString::fromStdString(stream_url);
    
    // Utiliser TCP par défaut pour la connexion RTSP (réglages UDP retirés)
    qDebug() << "[RTSP] Mode TCP (forcé)";
    qputenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp");
    
    // Open RTSP stream (les options sont prises via variable d'environnement)
    capture_ = std::make_unique<cv::VideoCapture>();
    capture_->open(stream_url, cv::CAP_FFMPEG);
    
    if (!capture_->isOpened()) {
        qDebug() << "[RTSP] ERREUR: Impossible d'ouvrir le flux";
        video_label_->setText("Erreur: Impossible de se connecter au flux RTSP");
        return;
    }
    
    qDebug() << "[RTSP] Flux ouvert avec succès";
    
    // Appliquer les paramètres pour réduire la latence
    applyStreamSettings();
    
    is_connected_ = true;
    connect_button_->setEnabled(false);
    disconnect_button_->setEnabled(true);
    url_input_->setEnabled(false);
    
    // Start frame timer à 30 FPS (33ms)
    frame_timer_->start(33);
}

void RtspViewer::disconnectStream()
{
    if (capture_ && capture_->isOpened()) {
        capture_->release();
    }
    capture_.reset();
    
    frame_timer_->stop();
    is_connected_ = false;
    
    connect_button_->setEnabled(true);
    disconnect_button_->setEnabled(false);
    url_input_->setEnabled(true);
    
    video_label_->setText("Déconnecté");
}

void RtspViewer::updateFrame()
{
    if (!capture_ || !capture_->isOpened()) {
        disconnectStream();
        return;
    }
    
    // Vider le buffer de manière agressive pour avoir l'image la plus récente
    // Essayer de skip jusqu'à 10 frames, ou le nombre configuré si plus élevé
    int max_skip = std::max(frame_skip_count_, 3);
    for (int i = 0; i < max_skip + 5; i++) {
        if (!capture_->grab()) {
            break;
        }
    }
    
    // Récupérer la dernière frame (la plus récente)
    cv::Mat frame;
    if (!capture_->retrieve(frame)) {
        return;
    }
    
    if (frame.empty() || frame.cols == 0 || frame.rows == 0) {
        return;
    }
    
    // Vérifier que l'image est valide et dans un format correct
    if (frame.type() != CV_8UC3 && frame.type() != CV_8UC1) {
        // Convertir en format compatible si nécessaire
        try {
            cv::Mat temp;
            frame.convertTo(temp, CV_8UC3);
            frame = temp;
        } catch (...) {
            return;
        }
    }
    
    // Si format incorrect, essayer de le réparer
    if (frame.channels() != 3 && frame.channels() != 1) {
        return;
    }
    
    // Réduire la résolution si activé (réduit latence)
    if (reduce_resolution_ && frame.cols > 320 && frame.rows > 240) {
        try {
            cv::Mat resized;
            int new_width = frame.cols / 2;
            int new_height = frame.rows / 2;
            if (new_width > 0 && new_height > 0) {
                cv::resize(frame, resized, cv::Size(new_width, new_height), 0, 0, cv::INTER_NEAREST);
                frame = resized;
            }
        } catch (const cv::Exception& e) {
            // Ignorer l'erreur de resize et garder la frame originale
        }
    }
    
    // Convert to QImage and display
    QImage qimg = mat2QImage(frame);
    video_label_->setPixmap(QPixmap::fromImage(qimg));
}

void RtspViewer::onConnectClicked()
{
    QString url = url_input_->text();
    if (!url.isEmpty()) {
        connectToStream(url);
    }
}

void RtspViewer::onDisconnectClicked()
{
    disconnectStream();
}

QImage RtspViewer::mat2QImage(const cv::Mat& mat)
{
    if (mat.empty() || mat.cols == 0 || mat.rows == 0) {
        return QImage();
    }
    
    cv::Mat rgb;
    
    try {
        // Gérer différents formats d'entrée
        if (mat.channels() == 1) {
            // Grayscale -> RGB
            cv::cvtColor(mat, rgb, cv::COLOR_GRAY2RGB);
        } else if (mat.channels() == 3) {
            // BGR -> RGB
            cv::cvtColor(mat, rgb, cv::COLOR_BGR2RGB);
        } else if (mat.channels() == 4) {
            // BGRA -> RGB
            cv::cvtColor(mat, rgb, cv::COLOR_BGRA2RGB);
        } else {
            return QImage();
        }
        
        // Vérifier que la conversion a fonctionné
        if (rgb.empty() || rgb.type() != CV_8UC3) {
            return QImage();
        }
        
        // Compression JPEG pour réduire la charge (si qualité < 100%)
        if (jpeg_quality_ < 100) {
            std::vector<uchar> buf;
            std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, jpeg_quality_};
            if (cv::imencode(".jpg", rgb, buf, params)) {
                cv::Mat decoded = cv::imdecode(buf, cv::IMREAD_COLOR);
                if (!decoded.empty()) {
                    rgb = decoded;
                }
            }
        }
        
        // Vérifier l'alignement des données (step doit être >= cols * 3)
        if (rgb.step < static_cast<size_t>(rgb.cols * 3)) {
            cv::Mat continuous;
            rgb.copyTo(continuous);
            rgb = continuous;
        }
        
        // Create QImage avec vérifications
        QImage img(rgb.data, rgb.cols, rgb.rows, static_cast<int>(rgb.step), QImage::Format_RGB888);
        
        // Deep copy to avoid data corruption
        return img.copy();
        
    } catch (const cv::Exception& e) {
        return QImage();
    } catch (...) {
        return QImage();
    }
}

void RtspViewer::setupLatencyControls()
{
    // Quality Slider (30-100%)
    quality_slider_->setRange(30, 100);
    quality_slider_->setValue(40);
    quality_slider_->setTickPosition(QSlider::TicksBelow);
    quality_slider_->setTickInterval(10);
    quality_slider_->setFixedWidth(120);
    quality_label_->setFixedWidth(90);
    quality_label_->setText("Qualité: 40%");
    
    // Skip Frames Slider (0-8 frames pour latence ultra-faible)
    skip_frames_slider_->setRange(0, 8);
    skip_frames_slider_->setValue(3);
    skip_frames_slider_->setTickPosition(QSlider::TicksBelow);
    skip_frames_slider_->setTickInterval(1);
    skip_frames_slider_->setFixedWidth(120);
    skip_frames_label_->setFixedWidth(90);
    skip_frames_label_->setText("Skip: 3");
    
    // Reduce resolution checkbox
    reduce_resolution_checkbox_->setChecked(true);
    
    // Protocol combo box (TCP only)
    protocol_combo_->addItem("🐌 TCP (Stable)", "tcp");
    protocol_combo_->setCurrentIndex(0);  // TCP par défaut
    protocol_combo_->setFixedWidth(150);
    protocol_label_->setStyleSheet("QLabel { font-weight: bold; }");
    
    // Settings layout
    settings_layout_->addWidget(new QLabel("⚡ Latence:"));
    settings_layout_->addWidget(quality_label_);
    settings_layout_->addWidget(quality_slider_);
    settings_layout_->addSpacing(15);
    settings_layout_->addWidget(skip_frames_label_);
    settings_layout_->addWidget(skip_frames_slider_);
    settings_layout_->addSpacing(15);
    settings_layout_->addWidget(reduce_resolution_checkbox_);
    settings_layout_->addSpacing(15);
    settings_layout_->addWidget(protocol_label_);
    settings_layout_->addWidget(protocol_combo_);
    settings_layout_->addStretch();
    
    // Style
    QString slider_style = "QSlider::groove:horizontal { background: #404040; height: 6px; border-radius: 3px; }"
    
                          "QSlider::handle:horizontal { background: #00aaff; width: 16px; margin: -5px 0; border-radius: 8px; }";
    quality_slider_->setStyleSheet(slider_style);
    skip_frames_slider_->setStyleSheet(slider_style);
    
    // Connect signals
    connect(quality_slider_, &QSlider::valueChanged, this, &RtspViewer::onQualityChanged);
    connect(reduce_resolution_checkbox_, &QCheckBox::toggled, this, &RtspViewer::onReduceResolutionToggled);
    connect(skip_frames_slider_, &QSlider::valueChanged, this, &RtspViewer::onSkipFramesChanged);
    connect(protocol_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &RtspViewer::onProtocolChanged);
}

void RtspViewer::applyStreamSettings()
{
    if (!capture_ || !capture_->isOpened()) return;
    
    qDebug() << "[RTSP] Application des paramètres de latence";
    qDebug() << "[RTSP] - Buffer size: 0";
    qDebug() << "[RTSP] - Skip frames:" << frame_skip_count_;
    qDebug() << "[RTSP] - Qualité JPEG:" << jpeg_quality_ << "%";
    qDebug() << "[RTSP] - Résolution réduite:" << (reduce_resolution_ ? "OUI" : "NON");
    
    // Buffer = 0 pour latence minimale (pas de frames en attente)
    capture_->set(cv::CAP_PROP_BUFFERSIZE, 0);
    
    // Timeouts courts pour ne pas attendre
    capture_->set(cv::CAP_PROP_OPEN_TIMEOUT_MSEC, 3000);
    capture_->set(cv::CAP_PROP_READ_TIMEOUT_MSEC, 1000);
    
    // Forcer décodage rapide si possible
    capture_->set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M','J','P','G'));
}

void RtspViewer::onQualityChanged(int value)
{
    jpeg_quality_ = value;
    quality_label_->setText(QString("Qualité: %1%").arg(value));
}

void RtspViewer::onReduceResolutionToggled(bool checked)
{
    reduce_resolution_ = checked;
}

void RtspViewer::onSkipFramesChanged(int value)
{
    frame_skip_count_ = value;
    skip_frames_label_->setText(QString("Skip: %1").arg(value));
}

void RtspViewer::onProtocolChanged(int index)
{
    protocol_type_ = protocol_combo_->itemData(index).toString();
    
    // Si déjà connecté, reconnecter avec le nouveau protocole
    if (is_connected_) {
        QString current_url = url_input_->text();
        disconnectStream();
        connectToStream(current_url);
    }
}
