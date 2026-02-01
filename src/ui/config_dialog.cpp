#include "ui/config_dialog.h"
#include <QLabel>
#include <QFileDialog>
#include <QMessageBox>
#include <QHeaderView>
#include <QDialogButtonBox>

ConfigDialog::ConfigDialog(QWidget *parent)
    : QDialog(parent)
    , tab_widget_(new QTabWidget(this))
{
    setWindowTitle("Configuration CAPRA UI");
    resize(700, 500);
    
    setupUI();
    loadFromConfig();
}

ConfigDialog::~ConfigDialog()
{
}

void ConfigDialog::setupUI()
{
    QVBoxLayout* main_layout = new QVBoxLayout(this);
    
    // ===== ROS Topics Tab =====
    ros_tab_ = new QWidget();
    QFormLayout* ros_layout = new QFormLayout(ros_tab_);
    
    pointcloud_topic_ = new QLineEdit();
    pose_topic_ = new QLineEdit();
    image_topic_ = new QLineEdit();
    
    ros_layout->addRow("Topic Nuages de Points:", pointcloud_topic_);
    ros_layout->addRow("Topic Position Robot:", pose_topic_);
    ros_layout->addRow("Topic Image:", image_topic_);
    
    QLabel* ros_note = new QLabel(
        "<i>Note: Les changements nécessitent de se réabonner aux topics</i>");
    ros_note->setWordWrap(true);
    ros_layout->addRow(ros_note);
    
    tab_widget_->addTab(ros_tab_, "Topics ROS");
    

    
    // ===== Map Tab =====
    map_tab_ = new QWidget();
    QFormLayout* map_layout = new QFormLayout(map_tab_);
    
    map_lat_ = new QDoubleSpinBox();
    map_lat_->setRange(-90.0, 90.0);
    map_lat_->setDecimals(6);
    
    map_lon_ = new QDoubleSpinBox();
    map_lon_->setRange(-180.0, 180.0);
    map_lon_->setDecimals(6);
    
    map_zoom_ = new QSpinBox();
    map_zoom_->setRange(1, 18);
    
    map_type_ = new QComboBox();
    map_type_->addItems({"satellite", "roadmap", "hybrid", "terrain"});
    
    map_layout->addRow("Latitude:", map_lat_);
    map_layout->addRow("Longitude:", map_lon_);
    map_layout->addRow("Zoom:", map_zoom_);
    map_layout->addRow("Type de carte:", map_type_);
    
    tab_widget_->addTab(map_tab_, "Carte");
    
    // ===== Panels Tab =====
    panels_tab_ = new QWidget();
    QVBoxLayout* panels_layout = new QVBoxLayout(panels_tab_);
    
    panels_table_ = new QTableWidget();
    panels_table_->setColumnCount(3);
    panels_table_->setHorizontalHeaderLabels({"Type", "Titre", "Activé"});
    panels_table_->horizontalHeader()->setStretchLastSection(true);
    
    QHBoxLayout* panel_buttons = new QHBoxLayout();
    add_panel_btn_ = new QPushButton("Ajouter");
    remove_panel_btn_ = new QPushButton("Supprimer");
    panel_buttons->addWidget(add_panel_btn_);
    panel_buttons->addWidget(remove_panel_btn_);
    panel_buttons->addStretch();
    
    panels_layout->addWidget(panels_table_);
    panels_layout->addLayout(panel_buttons);
    
    QLabel* panel_note = new QLabel(
        "<i>Types disponibles: pointcloud, map<br>"
        "L'ordre des panels définit l'ordre des onglets</i>");
    panel_note->setWordWrap(true);
    panels_layout->addWidget(panel_note);
    
    connect(add_panel_btn_, &QPushButton::clicked, this, &ConfigDialog::onAddPanel);
    connect(remove_panel_btn_, &QPushButton::clicked, this, &ConfigDialog::onRemovePanel);
    
    tab_widget_->addTab(panels_tab_, "Panneaux UI");
    
    // ===== General Tab =====
    general_tab_ = new QWidget();
    QVBoxLayout* general_layout = new QVBoxLayout(general_tab_);
    
    QFormLayout* general_form = new QFormLayout();
    
    refresh_rate_ = new QSpinBox();
    refresh_rate_->setRange(1, 120);
    refresh_rate_->setSuffix(" Hz");
    
    auto_connect_ = new QCheckBox("Connexion automatique au démarrage");
    
    config_path_ = new QLineEdit();
    config_path_->setReadOnly(true);
    
    general_form->addRow("Taux de rafraîchissement:", refresh_rate_);
    general_form->addRow(auto_connect_);
    general_form->addRow("Fichier de configuration:", config_path_);
    
    general_layout->addLayout(general_form);
    
    QGroupBox* config_group = new QGroupBox("Gestion de la configuration");
    QHBoxLayout* config_buttons = new QHBoxLayout(config_group);
    
    load_config_btn_ = new QPushButton("Charger...");
    save_config_btn_ = new QPushButton("Sauvegarder...");
    reset_btn_ = new QPushButton("Réinitialiser");
    
    config_buttons->addWidget(load_config_btn_);
    config_buttons->addWidget(save_config_btn_);
    config_buttons->addWidget(reset_btn_);
    config_buttons->addStretch();
    
    general_layout->addWidget(config_group);
    general_layout->addStretch();
    
    connect(load_config_btn_, &QPushButton::clicked, this, &ConfigDialog::onLoadConfig);
    connect(save_config_btn_, &QPushButton::clicked, this, &ConfigDialog::onSaveConfig);
    connect(reset_btn_, &QPushButton::clicked, this, &ConfigDialog::onResetToDefaults);
    
    tab_widget_->addTab(general_tab_, "Général");
    
    // ===== Dialog Buttons =====
    QDialogButtonBox* button_box = new QDialogButtonBox(
        QDialogButtonBox::Ok | QDialogButtonBox::Cancel | QDialogButtonBox::Apply);
    
    ok_button_ = button_box->button(QDialogButtonBox::Ok);
    cancel_button_ = button_box->button(QDialogButtonBox::Cancel);
    apply_button_ = button_box->button(QDialogButtonBox::Apply);
    
    connect(button_box, &QDialogButtonBox::accepted, this, &ConfigDialog::onAccepted);
    connect(button_box, &QDialogButtonBox::rejected, this, &ConfigDialog::onRejected);
    connect(apply_button_, &QPushButton::clicked, this, [this]() {
        saveToConfig();
        ConfigManager::instance().saveConfig();
    });
    
    // Main Layout
    main_layout->addWidget(tab_widget_);
    main_layout->addWidget(button_box);
}

void ConfigDialog::loadFromConfig()
{
    ConfigManager& config = ConfigManager::instance();
    
    // ROS Topics
    pointcloud_topic_->setText(config.getPointCloudTopic());
    pose_topic_->setText(config.getPoseTopic());
    image_topic_->setText(config.getImageTopic());
    

    
    // Map
    map_lat_->setValue(config.getMapLatitude());
    map_lon_->setValue(config.getMapLongitude());
    map_zoom_->setValue(config.getMapZoom());
    map_type_->setCurrentText(config.getMapType());
    
    // Panels
    panels_table_->setRowCount(0);
    QList<ConfigManager::PanelConfig> panels = config.getPanels();
    for (const auto& panel : panels) {
        int row = panels_table_->rowCount();
        panels_table_->insertRow(row);
        panels_table_->setItem(row, 0, new QTableWidgetItem(panel.type));
        panels_table_->setItem(row, 1, new QTableWidgetItem(panel.title));
        
        QCheckBox* checkbox = new QCheckBox();
        checkbox->setChecked(panel.enabled);
        panels_table_->setCellWidget(row, 2, checkbox);
    }
    
    // General
    refresh_rate_->setValue(config.getRefreshRate());
    auto_connect_->setChecked(config.getAutoConnect());
    config_path_->setText(config.getConfigFilePath());
}

void ConfigDialog::saveToConfig()
{
    ConfigManager& config = ConfigManager::instance();
    
    // ROS Topics
    config.setPointCloudTopic(pointcloud_topic_->text());
    config.setPoseTopic(pose_topic_->text());
    config.setImageTopic(image_topic_->text());

    
    // Map
    config.setMapCenter(map_lat_->value(), map_lon_->value(), map_zoom_->value());
    config.setMapType(map_type_->currentText());
    
    // Panels
    QList<ConfigManager::PanelConfig> panels;
    for (int row = 0; row < panels_table_->rowCount(); ++row) {
        ConfigManager::PanelConfig panel;
        panel.type = panels_table_->item(row, 0)->text();
        panel.title = panels_table_->item(row, 1)->text();
        
        QCheckBox* checkbox = qobject_cast<QCheckBox*>(panels_table_->cellWidget(row, 2));
        panel.enabled = checkbox ? checkbox->isChecked() : true;
        
        panels.append(panel);
    }
    config.setPanels(panels);
    
    // General
    config.setRefreshRate(refresh_rate_->value());
    config.setAutoConnect(auto_connect_->isChecked());
}

void ConfigDialog::onAccepted()
{
    saveToConfig();
    ConfigManager::instance().saveConfig();
    accept();
}

void ConfigDialog::onRejected()
{
    reject();
}



void ConfigDialog::onAddPanel()
{
    int row = panels_table_->rowCount();
    panels_table_->insertRow(row);
    panels_table_->setItem(row, 0, new QTableWidgetItem("pointcloud"));
    panels_table_->setItem(row, 1, new QTableWidgetItem("Nouveau Panel"));
    
    QCheckBox* checkbox = new QCheckBox();
    checkbox->setChecked(true);
    panels_table_->setCellWidget(row, 2, checkbox);
}

void ConfigDialog::onRemovePanel()
{
    int row = panels_table_->currentRow();
    if (row >= 0) {
        panels_table_->removeRow(row);
    }
}

void ConfigDialog::onLoadConfig()
{
    QString filename = QFileDialog::getOpenFileName(
        this, "Charger Configuration", "", "JSON Files (*.json);;All Files (*)");
    
    if (!filename.isEmpty()) {
        if (ConfigManager::instance().loadConfig(filename)) {
            loadFromConfig();
            QMessageBox::information(this, "Succès", 
                "Configuration chargée avec succès");
        } else {
            QMessageBox::warning(this, "Erreur", 
                "Impossible de charger la configuration");
        }
    }
}

void ConfigDialog::onSaveConfig()
{
    saveToConfig();
    
    QString filename = QFileDialog::getSaveFileName(
        this, "Sauvegarder Configuration", "", "JSON Files (*.json);;All Files (*)");
    
    if (!filename.isEmpty()) {
        if (ConfigManager::instance().saveConfig(filename)) {
            QMessageBox::information(this, "Succès", 
                "Configuration sauvegardée avec succès");
        } else {
            QMessageBox::warning(this, "Erreur", 
                "Impossible de sauvegarder la configuration");
        }
    }
}

void ConfigDialog::onResetToDefaults()
{
    QMessageBox::StandardButton reply = QMessageBox::question(
        this, "Réinitialiser", 
        "Êtes-vous sûr de vouloir réinitialiser à la configuration par défaut?",
        QMessageBox::Yes | QMessageBox::No);
    
    if (reply == QMessageBox::Yes) {
        // Create a temporary ConfigManager with default config
        ConfigManager& config = ConfigManager::instance();
        QJsonObject empty;
        config.setFullConfig(empty);
        
        // This will trigger creating default config
        QString temp_path = config.getConfigFilePath() + ".tmp";
        config.saveConfig(temp_path);
        config.loadConfig(temp_path);
        QFile::remove(temp_path);
        
        loadFromConfig();
    }
}

