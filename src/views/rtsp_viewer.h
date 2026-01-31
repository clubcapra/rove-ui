#ifndef RTSP_VIEWER_H
#define RTSP_VIEWER_H

#include <QWidget>
#include <QLabel>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLineEdit>
#include <QPushButton>
#include <QTimer>
#include <QImage>
#include <QSlider>
#include <QCheckBox>
#include <QComboBox>
#include <opencv2/opencv.hpp>
#include <memory>

class RtspViewer : public QWidget
{
    Q_OBJECT

public:
    explicit RtspViewer(QWidget *parent = nullptr);
    ~RtspViewer();

public slots:
    void connectToStream(const QString& url);
    void disconnectStream();

private slots:
    void updateFrame();
    void onConnectClicked();
    void onDisconnectClicked();

private:
    QVBoxLayout* main_layout_;
    QHBoxLayout* control_layout_;
    QHBoxLayout* settings_layout_;
    QLabel* video_label_;
    QLineEdit* url_input_;
    QPushButton* connect_button_;
    QPushButton* disconnect_button_;
    QTimer* frame_timer_;
    
    // Contrôles de latence
    QSlider* quality_slider_;
    QLabel* quality_label_;
    QCheckBox* reduce_resolution_checkbox_;
    QLabel* skip_frames_label_;
    QSlider* skip_frames_slider_;
    QComboBox* protocol_combo_;
    QLabel* protocol_label_;
    
    std::unique_ptr<cv::VideoCapture> capture_;
    bool is_connected_;
    int jpeg_quality_;
    bool reduce_resolution_;
    int frame_skip_count_;
    QString protocol_type_;  // "tcp" (only TCP supported)
    
    QImage mat2QImage(const cv::Mat& mat);
    void setupLatencyControls();
    void applyStreamSettings();
    
private slots:
    void onQualityChanged(int value);
    void onReduceResolutionToggled(bool checked);
    void onSkipFramesChanged(int value);
    void onProtocolChanged(int index);
};

#endif // RTSP_VIEWER_H
