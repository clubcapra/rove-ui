#ifndef CONFIG_DIALOG_H
#define CONFIG_DIALOG_H

#include <QDialog>
#include <QTabWidget>
#include <QLineEdit>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QComboBox>
#include <QCheckBox>
#include <QTableWidget>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QGroupBox>
#include "core/config_manager.h"

class ConfigDialog : public QDialog
{
    Q_OBJECT

public:
    explicit ConfigDialog(QWidget *parent = nullptr);
    ~ConfigDialog();

private slots:
    void onAccepted();
    void onRejected();
    void onAddRtspStream();
    void onRemoveRtspStream();
    void onAddPanel();
    void onRemovePanel();
    void onLoadConfig();
    void onSaveConfig();
    void onResetToDefaults();

private:
    void setupUI();
    void loadFromConfig();
    void saveToConfig();
    
    // Tabs
    QTabWidget* tab_widget_;
    
    // ROS Topics Tab
    QWidget* ros_tab_;
    QLineEdit* pointcloud_topic_;
    QLineEdit* pose_topic_;
    QLineEdit* image_topic_;
    
    // RTSP Streams Tab
    QWidget* rtsp_tab_;
    QTableWidget* rtsp_table_;
    QPushButton* add_rtsp_btn_;
    QPushButton* remove_rtsp_btn_;
    
    // Map Tab
    QWidget* map_tab_;
    QDoubleSpinBox* map_lat_;
    QDoubleSpinBox* map_lon_;
    QSpinBox* map_zoom_;
    QComboBox* map_type_;
    
    // Panels Tab
    QWidget* panels_tab_;
    QTableWidget* panels_table_;
    QPushButton* add_panel_btn_;
    QPushButton* remove_panel_btn_;
    
    // General Tab
    QWidget* general_tab_;
    QSpinBox* refresh_rate_;
    QCheckBox* auto_connect_;
    QLineEdit* config_path_;
    QPushButton* load_config_btn_;
    QPushButton* save_config_btn_;
    QPushButton* reset_btn_;
    
    // Buttons
    QPushButton* ok_button_;
    QPushButton* cancel_button_;
    QPushButton* apply_button_;
};

#endif // CONFIG_DIALOG_H
