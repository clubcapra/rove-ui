#ifndef CONFIG_MANAGER_H
#define CONFIG_MANAGER_H

#include <QObject>
#include <QString>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QMap>
#include <QVariant>

class ConfigManager : public QObject
{
    Q_OBJECT

public:
    static ConfigManager& instance();
    
    // Load/Save configuration
    bool loadConfig(const QString& filepath = "");
    bool saveConfig(const QString& filepath = "");
    
    // ROS Topics
    QString getPointCloudTopic() const;
    QString getPoseTopic() const;
    QString getImageTopic() const;
    
    void setPointCloudTopic(const QString& topic);
    void setPoseTopic(const QString& topic);
    void setImageTopic(const QString& topic);
    
    
   
    
    // Map Settings
    double getMapLatitude() const;
    double getMapLongitude() const;
    int getMapZoom() const;
    QString getMapType() const;
    
    void setMapCenter(double lat, double lon, int zoom);
    void setMapType(const QString& type);
    
    // UI Layout
    struct PanelConfig {
        QString type;  // "pointcloud", "map", "rtsp", "custom", "layout"
        QString title;
        bool enabled;
        QMap<QString, QVariant> properties;
        
        // Pour les layouts de type "grid"
        QString layout_type;  // "grid", "horizontal", "vertical"
        int rows;
        int columns;
        QList<PanelConfig> children;  // Panels contenus dans ce layout
    };
    
    QList<PanelConfig> getPanels() const;
    void setPanels(const QList<PanelConfig>& panels);
    
    // General Settings
    QString getConfigFilePath() const;
    int getRefreshRate() const;
    bool getAutoConnect() const;

    
    void setRefreshRate(int hz);
    void setAutoConnect(bool autoConnect);
    
    // Get raw JSON for advanced usage
    QJsonObject getFullConfig() const;
    void setFullConfig(const QJsonObject& config);

signals:
    void configChanged();
    void configLoadError(const QString& error);
    void configSaved(const QString& filepath);

private:
    ConfigManager();
    ~ConfigManager();
    ConfigManager(const ConfigManager&) = delete;
    ConfigManager& operator=(const ConfigManager&) = delete;
    
    QJsonObject config_;
    QString config_file_path_;
    
    void createDefaultConfig();
    PanelConfig parsePanelConfig(const QJsonObject& obj) const;
    QJsonObject getSection(const QString& section) const;
    void setSection(const QString& section, const QJsonObject& data);
};

#endif // CONFIG_MANAGER_H
