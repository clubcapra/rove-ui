# CAPRA_UI - Interface de contrôle robotique

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Qt](https://img.shields.io/badge/Qt-6.4.2-green)
![ROS2](https://img.shields.io/badge/ROS2-Humble-orange)

## 📋 Description

CAPRA_UI est une application Qt6 pour le contrôle et la visualisation de robots autonomes. Elle intègre :

-  **Cartes satellites interactives** (Leaflet.js)
-  **Flux vidéo RTSP** (caméras multiples)
-  **Visualisation de nuages de points 3D** (PCL + VTK) à valider
-  **Intégration ROS 2** (rclcpp, sensor_msgs, geometry_msgs)
-  **Configuration JSON** complète et flexible

## 📁 Structure du projet

```
CAPRA_UI/
├── src/
│   ├── core/              # Logique métier et configuration
│   │   ├── config_manager.cpp
│   │   └── config_manager.h
│   ├── adapters/          # Intégrations externes (ROS 2, etc.)
│   │   ├── ros_node.cpp
│   │   └── ros_node.h
│   ├── views/             # Widgets de visualisation
│   │   ├── map_viewer.cpp/h
│   │   ├── rtsp_viewer.cpp/h
│   │   └── pointcloud_viewer.cpp/h
│   ├── ui/                # Interface utilisateur
│   │   ├── capra_ui.cpp/h/ui
│   │   └── config_dialog.cpp/h
│   └── main.cpp
├── tests/
│   ├── unit/              # Tests unitaires
│   ├── integration/       # Tests d'intégration
│   └── CMakeLists.txt
├── docs/                  # Documentation
├── examples/              # Exemples de configuration
│   └── config.json
├── build/                 # Build ROS 2
├── build_standalone/      # Build standalone
└── CMakeLists.txt
```

## 🚀 Démarrage rapide

### Mode Standalone (sans ROS 2)

```bash
chmod +x ./launch.sh
./launch.sh
```



## ⚙️ Configuration

La configuration se fait via un fichier JSON situé à :
```json
{
    "general": {
        "auto_connect": false,
        "language": "fr_CA",
        "refresh_rate": 30
    },
    "map": {
        "latitude": 45.5017,
        "longitude": -73.5673,
        "type": "satellite",
        "zoom": 13
    },
    "panels": [
        {
            "enabled": true,
            "title": "Vue Principale - Grille 2x2",
            "type": "layout",
            "layout_type": "grid",
            "rows": 2,
            "columns": 2,
            "children": [
                {
                    "enabled": true,
                    "title": "Nuage de Points 3D",
                    "type": "pointcloud",
                    "properties": {
                        "mock_mode": true
                    }
                },
                {
                    "enabled": true,
                    "title": "Carte",
                    "type": "map"
                },
                {
                    "enabled": true,
                    "title": "Caméra Avant",
                    "type": "rtsp",
                    "properties": {
                        "stream_index": 0
                    }
                },
                {
                    "enabled": true,
                    "title": "Caméra Arrière",
                    "type": "rtsp",
                    "properties": {
                        "stream_index": 1
                    }
                }
            ]
        },
        {
            "enabled": true,
            "title": "Vue Horizontale - Caméras",
            "type": "layout",
            "layout_type": "horizontal",
            "rows": 1,
            "columns": 3,
            "children": [
                {
                    "enabled": true,
                    "title": "Caméra 1",
                    "type": "rtsp",
                    "properties": {
                        "stream_index": 0
                    }
                },
                {
                    "enabled": true,
                    "title": "Caméra 2",
                    "type": "rtsp",
                    "properties": {
                        "stream_index": 1
                    }
                },
                {
                    "enabled": true,
                    "title": "Nuage Points",
                    "type": "pointcloud",
                    "properties": {
                        "mock_mode": true
                    }
                }
            ]
        },
        {
            "enabled": true,
            "title": "Vue Mixte - Layout Imbriqué",
            "type": "layout",
            "layout_type": "vertical",
            "rows": 2,
            "columns": 1,
            "children": [
                {
                    "enabled": true,
                    "title": "Carte Plein Écran",
                    "type": "map"
                },
                {
                    "enabled": true,
                    "title": "Sous-grille 1x2",
                    "type": "layout",
                    "layout_type": "grid",
                    "rows": 1,
                    "columns": 2,
                    "children": [
                        {
                            "enabled": true,
                            "title": "Points 3D",
                            "type": "pointcloud",
                            "properties": {
                                "mock_mode": true
                            }
                        },
                        {
                            "enabled": true,
                            "title": "RTSP",
                            "type": "rtsp",
                            "properties": {
                                "stream_index": 0
                            }
                        }
                    ]
                }
            ]
        }
    ],
    "ros_topics": {
        "image": "/camera/image_raw",
        "pointcloud": "/pointcloud",
        "pose": "/robot_pose"
    },
    "rtsp_streams": [
        {
            "enabled": true,
            "name": "Caméra Avant",
            "url": "rtsp://192.168.168.22:554/stream1"
        },
        {
            "enabled": true,
            "name": "Caméra Arrière",
            "url": "rtsp://192.168.168.22:554/stream1"
        },
        {
            "enabled": false,
            "name": "Caméra Latérale",
            "url": "rtsp://192.168.168.22:554/stream1"
        }
    ]
}

```
## 📦 Dépendances


### Optionnelles (mode ROS 2)
- ROS 2 Humble/Iron
- PCL (Point Cloud Library) ≥ 1.12
- VTK (Visualization Toolkit) ≥ 9.0
- sensor_msgs, geometry_msgs, pcl_conversions

## 🏗️ Architecture

### Core
- **ConfigManager** : Singleton de gestion de la configuration JSON

### Adapters
- **RosNode** : Pont entre ROS 2 et Qt (messages, topics)

### Views
- **MapViewer** : Carte Leaflet.js interactive
- **RtspViewer** : Affichage de flux RTSP avec OpenCV
- **PointCloudViewer** : Rendu 3D de nuages de points (PCL/VTK)

### UI
- **CapraUI** : Fenêtre principale avec layout dynamique
- **ConfigDialog** : Interface de configuration à 5 onglets

**Note** : Ce projet est en développement actif. L'API peut changer entre les versions.
