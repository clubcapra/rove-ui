# 🎨 CAPRA UI - Système de Layouts Dynamiques

## ✨ Nouveautés

### 📐 **Layouts Dynamiques 100% Configurables**

Tu peux maintenant créer des **interfaces complexes avec plusieurs panels dans une même vue**, entièrement via JSON !

#### Types de Layouts :
- **Grid** (Grille) : 2x2, 3x3, ou n'importe quelle taille
- **Horizontal** : Panels côte à côte avec splitters redimensionnables
- **Vertical** : Panels empilés avec splitters redimensionnables
- **Imbriqué** : Layouts dans des layouts pour des interfaces ultra-complexes !

## 🚀 Démarrage Rapide

### Compilation et lancement

```bash
# Compiler avec CMake
mkdir -p build_standalone && cd build_standalone
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Copier un exemple de configuration
cp examples/config_simple_grid.json ~/.config/CAPRA_UI/capra_ui_config.json

# Lancer l'application (mode standalone)
QT_QPA_PLATFORM=xcb ./CAPRA_UI
```

## 📝 Exemples de Configuration

### Grille 2x2 - Dashboard Complet
```json
{
    "panels": [{
        "type": "layout",
        "layout_type": "grid",
        "rows": 2,
        "columns": 2,
        "title": "Dashboard",
        "enabled": true,
        "children": [
            {"type": "pointcloud", "properties": {"mock_mode": true}},
            {"type": "map"},
            {"type": "rtsp", "properties": {"stream_index": 0}},
            {"type": "rtsp", "properties": {"stream_index": 1}}
        ]
    }]
}
```

### Vue Horizontale - Multi-Caméras
```json
{
    "panels": [{
        "type": "layout",
        "layout_type": "horizontal",
        "title": "Caméras",
        "enabled": true,
        "children": [
            {"type": "rtsp", "properties": {"stream_index": 0}},
            {"type": "pointcloud", "properties": {"mock_mode": true}},
            {"type": "rtsp", "properties": {"stream_index": 1}}
        ]
    }]
}
```

### Layout Imbriqué Avancé
```json
{
    "panels": [{
        "type": "layout",
        "layout_type": "vertical",
        "title": "Vue Complexe",
        "enabled": true,
        "children": [
            {"type": "map"},
            {
                "type": "layout",
                "layout_type": "grid",
                "rows": 1,
                "columns": 2,
                "children": [
                    {"type": "pointcloud", "properties": {"mock_mode": true}},
                    {"type": "rtsp", "properties": {"stream_index": 0}}
                ]
            }
        ]
    }]
}
```

## 🎯 Cas d'Utilisation

### 1. **Surveillance Multi-Caméras**
Grille 2x3 ou 3x2 avec 6 flux RTSP simultanés

### 2. **Pilotage Robot**
- Top : Carte de navigation
- Bottom : Grille avec nuage 3D + 2 caméras

### 3. **Monitoring Complet**
Grille 2x2 :
- Nuage de points 3D
- Carte GPS
- Caméra avant
- Caméra arrière

### 4. **Vue Cinéma**
Layout horizontal avec 3-4 caméras côte à côte

## 🎨 Contrôles Nuage de Points 3D

Le visualiseur de nuages de points inclut des contrôles interactifs :

- **Taille des particules** : Slider 0.1 - 10.0
- **Modes de couleur** : 6 presets (Arc-en-ciel, Feu, Glace, Nature, Néon, Monochrome)
- **Vitesse d'animation** : Slider 0.1x - 5.0x
- **Gradient** : Active/désactive les dégradés de couleur
- **Pause/Reprendre** : Contrôle l'animation

## 📚 Documentation Complète

- **[LAYOUTS.md](docs/LAYOUTS.md)** - Guide complet des layouts
- **[MOCK_POINTCLOUD.md](docs/MOCK_POINTCLOUD.md)** - Guide du nuage de points 3D
- **[CONFIG_SUMMARY.md](docs/CONFIG_SUMMARY.md)** - Référence de configuration
- **[README.md](docs/README.md)** - Documentation générale

## 📦 Fichiers d'Exemple

- `examples/config_simple_grid.json` - Grille 2x2 simple
- `examples/config_with_layouts.json` - Layouts multiples avec imbrication
- `examples/config_with_mock.json` - Configuration avec mock point cloud
- `examples/config.json` - Configuration de base

## 🛠️ Structure du Projet

```
CAPRA_UI/
├── src/
│   ├── core/           # ConfigManager avec parsing récursif
│   ├── views/          # LayoutPanel + tous les viewers
│   ├── ui/             # Interface principale
│   └── adapters/       # ROS 2 (optionnel)
├── examples/           # Fichiers de config d'exemple
├── docs/              # Documentation
└── tests/             # Tests unitaires
```

## ⚙️ Compilation

### Mode Standalone (sans ROS 2)

```bash
mkdir -p build_standalone && cd build_standalone
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### Mode avec ROS 2

Compiler avec `colcon` dans un workspace ROS 2 est toujours possible :

```bash
# Exemple rapide (dans le workspace ROS 2)
colcon build --packages-select CAPRA_UI
```

## 🎓 Tips & Astuces

1. **Splitters redimensionnables** : Les layouts horizontal/vertical permettent de glisser les séparateurs !
2. **Imbrication** : Aucune limite - créez des layouts aussi complexes que nécessaire
3. **Performance** : Limitez-vous à ~9 panels actifs simultanément
4. **Hot reload** : Modifiez le JSON et relancez l'app - l'interface se reconstruit !

## 🔥 Fonctionnalités Clés

- ✅ **100% Dynamique** - Tout configurable en JSON
- ✅ **Layouts Imbriqués** - Profondeur infinie
- ✅ **Splitters** - Redimensionnement interactif
- ✅ **Multiple Viewers** - Pointcloud 3D, Map, RTSP, etc.
- ✅ **Mock Mode** - Fonctionne sans ROS 2
- ✅ **OpenGL 3D** - Vrai rendu 3D avec 5000+ points
- ✅ **Contrôles Interactifs** - Couleurs, tailles, vitesse

## 📄 License

Projet CAPRA - Interface de contrôle robot

## 🤝 Contribution

Les contributions sont bienvenues ! Voir la documentation pour ajouter de nouveaux types de panels.

---

**Fait avec ❤️ pour le projet CAPRA**
