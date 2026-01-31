# CAPRA_UI - Interface de contrôle robotique

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Qt](https://img.shields.io/badge/Qt-6.4.2-green)
![ROS2](https://img.shields.io/badge/ROS2-Humble-orange)

## 📋 Description

CAPRA_UI est une application Qt6 pour le contrôle et la visualisation de robots autonomes. Elle intègre :

- 🗺️ **Cartes satellites interactives** (Leaflet.js)
- 📹 **Flux vidéo RTSP** (caméras multiples)
- ☁️ **Visualisation de nuages de points 3D** (PCL + VTK)
- 🤖 **Intégration ROS 2** (rclcpp, sensor_msgs, geometry_msgs)
- ⚙️ **Configuration JSON** complète et flexible

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
│   │   ├── test_config_manager.cpp
│   │   ├── test_rtsp_viewer.cpp
│   │   └── test_map_viewer.cpp
│   ├── integration/       # Tests d'intégration
│   └── CMakeLists.txt
├── docs/                  # Documentation
│   ├── README.md
│   ├── CONFIGURATION_GUIDE.md
│   ├── QUICKSTART.md
│   └── ...
├── examples/              # Exemples de configuration
│   └── config.json
├── build/                 # Build ROS 2
├── build_standalone/      # Build standalone
└── CMakeLists.txt
```

## 🚀 Démarrage rapide

### Mode Standalone (sans ROS 2)

```bash
# Installer manuellement les dépendances requises (Qt6, OpenCV, CMake)
# Exemple (Debian/Ubuntu) :
# sudo apt install build-essential cmake libqt6* libopencv-dev

# Compilation avec CMake :
mkdir -p build_standalone && cd build_standalone
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Exécution
QT_QPA_PLATFORM=xcb ./CAPRA_UI
```

### Mode ROS 2

```bash
# Installation des dépendances
./install_dependencies.sh

# Compilation avec colcon
cd ~/CAPRA_UI
colcon build --packages-select CAPRA_UI

# Sourcer et exécuter
source install/setup.bash
ros2 run CAPRA_UI CAPRA_UI
```

## 🧪 Tests

```bash
# Compiler avec les tests
cd build_standalone
cmake .. -DBUILD_WITH_ROS2=OFF
make

# Exécuter tous les tests
make run_tests

# Ou exécuter individuellement
./tests/test_config_manager
./tests/test_rtsp_viewer
./tests/test_map_viewer
```

## ⚙️ Configuration

La configuration se fait via un fichier JSON situé à :
`~/.config/CAPRA_UI/capra_ui_config.json`

Exemple :

```json
{
    "general": {
        "auto_connect": true,
        "language": "fr_CA",
        "refresh_rate": 30
    },
    "rtsp_streams": [
        {
            "name": "Caméra Principale",
            "url": "rtsp://admin:123456@192.168.168.115:554/stream1",
            "enabled": true
        }
    ],
    "map": {
        "latitude": 45.5017,
        "longitude": -73.5673,
        "zoom": 13,
        "type": "satellite"
    }
}
```

Voir [CONFIGURATION_GUIDE.md](docs/CONFIGURATION_GUIDE.md) pour plus de détails.

## 📦 Dépendances

### Obligatoires (mode standalone)
- Qt6 (≥ 6.4) : Widgets, WebEngineWidgets
- OpenCV (≥ 4.6) : Streaming RTSP
- CMake (≥ 3.16)
- Google Test : Tests unitaires

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

## 📚 Documentation

- [Guide de démarrage rapide](docs/QUICKSTART.md)
- [Guide de configuration](docs/CONFIGURATION_GUIDE.md)
- [Voir l'interface sans ROS 2](docs/VOIR_INTERFACE.md)
- [Migration vers JSON](docs/MIGRATION_GUIDE.md)
- [Résumé de la config](docs/CONFIG_SUMMARY.md)

## 🐛 Dépannage

### Erreur WebEngine GPU
Si vous voyez `ContextResult::kTransientFailure`, c'est un avertissement bénin lié au GPU. L'application fonctionne normalement.

### Caméra RTSP ne se connecte pas
1. Testez avec VLC : `vlc rtsp://user:pass@ip:port/stream`
2. Vérifiez le chemin du stream (`/stream1`, `/h264`, `/live`, etc.)
3. Consultez les logs dans la console Qt

### Note sur le transport RTSP
Le viewer RTSP utilise désormais exclusivement le transport TCP (fiabilité). Le support UDP/UDP Multicast a été retiré du code car instable sur plusieurs environnements. Aucune configuration supplémentaire n'est nécessaire pour forcer TCP : l'application applique les options nécessaires au démarrage du flux.

### Tests échouent
```bash
# Mode verbose
cd build_standalone
ctest --output-on-failure
```

## 🤝 Contribution

Les contributions sont les bienvenues ! Veuillez :

1. Créer une branche pour votre fonctionnalité
2. Écrire des tests pour le nouveau code
3. Vérifier que tous les tests passent
4. Soumettre une pull request

## 📝 License

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.

## 📧 Contact

Pour toute question ou suggestion, ouvrez une issue sur le dépôt.

---

**Note** : Ce projet est en développement actif. L'API peut changer entre les versions.
