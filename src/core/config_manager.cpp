#include "core/config_manager.h"
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QStandardPaths>
#include <QDir>
#include <QDebug>

ConfigManager& ConfigManager::instance()
{
    static ConfigManager instance;
    return instance;
}

ConfigManager::ConfigManager()
{
    // Default config file in user's config directory
    QString config_dir = QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation);
    QDir().mkpath(config_dir);
    config_file_path_ = config_dir + "/capra_ui_config.json";
    
    // Try to load existing config, otherwise create default
    if (!loadConfig(config_file_path_)) {
        createDefaultConfig();
        saveConfig(config_file_path_);
    }
}

ConfigManager::~ConfigManager()
{
}

bool ConfigManager::loadConfig(const QString& filepath)
{
    QString path = filepath.isEmpty() ? config_file_path_ : filepath;
    
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        qWarning() << "Cannot open config file:" << path;
        emit configLoadError("Cannot open file: " + path);
        return false;
    }
    
    QByteArray data = file.readAll();
    file.close();
    
    QJsonParseError error;
    QJsonDocument doc = QJsonDocument::fromJson(data, &error);
    
    if (error.error != QJsonParseError::NoError) {
        qWarning() << "JSON parse error:" << error.errorString();
        emit configLoadError("JSON parse error: " + error.errorString());
        return false;
    }
    
    config_ = doc.object();
    config_file_path_ = path;
    
    emit configChanged();
    return true;
}

bool ConfigManager::saveConfig(const QString& filepath)
{
    QString path = filepath.isEmpty() ? config_file_path_ : filepath;
    
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly)) {
        qWarning() << "Cannot write config file:" << path;
        return false;
    }
    
    QJsonDocument doc(config_);
    file.write(doc.toJson(QJsonDocument::Indented));
    file.close();
    
    config_file_path_ = path;
    emit configSaved(path);
    
    return true;
}

void ConfigManager::createDefaultConfig()
{
    QJsonObject config;
    
    // ROS Topics
    QJsonObject ros_topics;
    ros_topics["pointcloud"] = "/pointcloud";
    ros_topics["pose"] = "/robot_pose";
    config["ros_topics"] = ros_topics;
    

    
    // Map Settings
    QJsonObject map_settings;
    map_settings["latitude"] = 45.5017;
    map_settings["longitude"] = -73.5673;
    map_settings["zoom"] = 13;
    map_settings["type"] = "satellite";
    config["map"] = map_settings;
    
    // UI Panels
    QJsonArray panels;
    
    QJsonObject panel1;
    panel1["type"] = "pointcloud";
    panel1["title"] = "Nuages de Points";
    panel1["enabled"] = true;
    panels.append(panel1);
    
    QJsonObject panel2;
    panel2["type"] = "map";
    panel2["title"] = "Carte Satellite";
    panel2["enabled"] = true;
    panels.append(panel2);
    


    
    config["panels"] = panels;
    
    // General Settings
    QJsonObject general;
    general["refresh_rate"] = 30;
    general["auto_connect"] = false;
    general["language"] = "fr_CA";
    config["general"] = general;
    
    config_ = config;
}

// ROS Topics
QString ConfigManager::getPointCloudTopic() const
{
    return config_["ros_topics"].toObject()["pointcloud"].toString("/pointcloud");
}

QString ConfigManager::getPoseTopic() const
{
    return config_["ros_topics"].toObject()["pose"].toString("/robot_pose");
}

QString ConfigManager::getImageTopic() const
{
    return config_["ros_topics"].toObject()["image"].toString("/camera/image_raw");
}

void ConfigManager::setPointCloudTopic(const QString& topic)
{
    QJsonObject ros_topics = config_["ros_topics"].toObject();
    ros_topics["pointcloud"] = topic;
    config_["ros_topics"] = ros_topics;
}

void ConfigManager::setPoseTopic(const QString& topic)
{
    QJsonObject ros_topics = config_["ros_topics"].toObject();
    ros_topics["pose"] = topic;
    config_["ros_topics"] = ros_topics;
}

void ConfigManager::setImageTopic(const QString& topic)
{
    QJsonObject ros_topics = config_["ros_topics"].toObject();
    ros_topics["image"] = topic;
    config_["ros_topics"] = ros_topics;
}


// Map Settings
double ConfigManager::getMapLatitude() const
{
    return config_["map"].toObject()["latitude"].toDouble(45.5017);
}

double ConfigManager::getMapLongitude() const
{
    return config_["map"].toObject()["longitude"].toDouble(-73.5673);
}

int ConfigManager::getMapZoom() const
{
    return config_["map"].toObject()["zoom"].toInt(13);
}

QString ConfigManager::getMapType() const
{
    return config_["map"].toObject()["type"].toString("satellite");
}

void ConfigManager::setMapCenter(double lat, double lon, int zoom)
{
    QJsonObject map = config_["map"].toObject();
    map["latitude"] = lat;
    map["longitude"] = lon;
    map["zoom"] = zoom;
    config_["map"] = map;
}

void ConfigManager::setMapType(const QString& type)
{
    QJsonObject map = config_["map"].toObject();
    map["type"] = type;
    config_["map"] = map;
}

// UI Panels
// Helper function to parse panel config recursively
ConfigManager::PanelConfig ConfigManager::parsePanelConfig(const QJsonObject& obj) const
{
    PanelConfig config;
    config.type = obj["type"].toString();
    config.title = obj["title"].toString();
    config.enabled = obj["enabled"].toBool(true);
    
    // Parse properties
    QJsonObject props = obj["properties"].toObject();
    for (const QString& key : props.keys()) {
        config.properties[key] = props[key].toVariant();
    }
    
    // Parse layout-specific fields
    if (config.type == "layout") {
        config.layout_type = obj["layout_type"].toString("grid");
        config.rows = obj["rows"].toInt(1);
        config.columns = obj["columns"].toInt(1);
        
        // Parse children panels recursively
        QJsonArray children = obj["children"].toArray();
        for (const QJsonValue& child : children) {
            config.children.append(parsePanelConfig(child.toObject()));
        }
    }
    
    return config;
}

QList<ConfigManager::PanelConfig> ConfigManager::getPanels() const
{
    QList<PanelConfig> panels;
    QJsonArray array = config_["panels"].toArray();
    
    for (const QJsonValue& value : array) {
        panels.append(parsePanelConfig(value.toObject()));
    }
    
    return panels;
}

void ConfigManager::setPanels(const QList<PanelConfig>& panels)
{
    QJsonArray array;
    
    for (const PanelConfig& panel : panels) {
        QJsonObject obj;
        obj["type"] = panel.type;
        obj["title"] = panel.title;
        obj["enabled"] = panel.enabled;
        
        // Convert properties to JSON
        QJsonObject props;
        for (auto it = panel.properties.begin(); it != panel.properties.end(); ++it) {
            props[it.key()] = QJsonValue::fromVariant(it.value());
        }
        obj["properties"] = props;
        
        array.append(obj);
    }
    
    config_["panels"] = array;
}

// General Settings
QString ConfigManager::getConfigFilePath() const
{
    return config_file_path_;
}

int ConfigManager::getRefreshRate() const
{
    return config_["general"].toObject()["refresh_rate"].toInt(30);
}

bool ConfigManager::getAutoConnect() const
{
    return config_["general"].toObject()["auto_connect"].toBool(false);
}


void ConfigManager::setRefreshRate(int hz)
{
    QJsonObject general = config_["general"].toObject();
    general["refresh_rate"] = hz;
    config_["general"] = general;
}

void ConfigManager::setAutoConnect(bool autoConnect)
{
    QJsonObject general = config_["general"].toObject();
    general["auto_connect"] = autoConnect;
    config_["general"] = general;
}

// Raw JSON access
QJsonObject ConfigManager::getFullConfig() const
{
    return config_;
}

void ConfigManager::setFullConfig(const QJsonObject& config)
{
    config_ = config;
    emit configChanged();
}

QJsonObject ConfigManager::getSection(const QString& section) const
{
    return config_[section].toObject();
}

void ConfigManager::setSection(const QString& section, const QJsonObject& data)
{
    config_[section] = data;
}
