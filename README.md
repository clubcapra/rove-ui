# Rove-UI

Interface de contrôle mission pour le rover CAPRA — PySide6, architecture config-driven, multi-écrans.

## Prérequis

- Ubuntu / WSL
- Python 3.12+
- pip
- Dépendance système Qt (xcb) :

```bash
sudo apt update
sudo apt install -y libxcb-cursor0
```

- Dépendance système GStreamer (nécessaire pour RTSP) :

```bash
sudo apt update
sudo apt install -y \
  python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-tools gstreamer1.0-gl gstreamer1.0-libav \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
```

## Installation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

> Si tu utilises `python3-gi` via `apt`, recrée le venv avec :
> ```bash
> python3 -m venv --system-site-packages .venv
> ```

## Lancement

```bash
./run.sh
```

Le script nettoie les variables Qt et choisit Wayland (WSLg) ou xcb (X11) automatiquement.

### Lancement manuel — Wayland (WSLg)

```bash
env -u QT_PLUGIN_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH -u LD_LIBRARY_PATH \
  XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir WAYLAND_DISPLAY=wayland-0 \
  QT_QPA_PLATFORM=wayland .venv/bin/python widget.py
```

### Lancement manuel — xcb (fallback)

```bash
env -u QT_PLUGIN_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH -u LD_LIBRARY_PATH \
  DISPLAY=:0 QT_QPA_PLATFORM=xcb .venv/bin/python widget.py
```

---

## Architecture générale

```
widget.py  (Widget)
├── Header          — barre de statut fixe (haut)
├── NavBar          — onglets de navigation (caché si 1 seule vue)
├── QStackedWidget  — zone principale
│   └── LayoutPanel × N  — une page par vue du config
└── ButtonBar       — barre d'actions persistante (bas, optionnelle)
```

Les vues et composants sont entièrement définis par des fichiers JSON dans `config/`. Un `EventBus` singleton relie tous les composants de façon découplée. Les deux fenêtres (`config_window1.json` et `config_window2.json`) partagent le même `EventBus` pour permettre la communication inter-fenêtres.

---

## Structure du fichier de config

```jsonc
{
  "header_settings": { ... },   // voir Header
  "udp_clients":     [ ... ],   // clients de données UDP
  "ros2_clients":    [ ... ],   // clients ROS2
  "console": true,              // active le log interne
  "bottom_bar":      { ... },   // voir ButtonBar (optionnel)
  "views": {
    "NOM_VUE": { "type": "layout", ... }   // voir LayoutPanel
  }
}
```

---

## Composants

### LayoutPanel

Conteneur racine de chaque vue. Interprète la config et instancie les composants enfants.

```jsonc
{
  "type": "layout",
  "diaposition": "horizontal" | "vertical" | "grid" | "absolute",

  // Pour "grid" uniquement :
  "grid": {
    "rows": 2,
    "columns": 2,
    "spacing": 6        // pixels entre les cellules
  },

  "data": { ... },      // données héritées par tous les enfants (merge profond)
  "content": [ ... ]    // liste de composants enfants
}
```

Chaque enfant peut recevoir une clé `"label"` pour afficher une barre-titre tactique :

```jsonc
{
  "type": "chart",
  "name": "mon_chart",
  "label": "TEMPÉRATURES",   // affiche "▸ TEMPÉRATURES" au-dessus du composant
  "data": { ... }
}
```

---

### Absolute layout — style par enfant

Quand `diaposition` vaut `"absolute"`, chaque enfant doit avoir une clé `"style"` :

| Clé | Type | Défaut | Description |
|-----|------|--------|-------------|
| `x` | px \| `"N%"` \| `"center"` | `0` | Position gauche (ou centrage horizontal) |
| `y` | px \| `"N%"` \| `"center"` | `0` | Position haute (ou centrage vertical) |
| `right` | px \| `"N%"` | — | Position depuis le bord droit (remplace `x`) |
| `bottom` | px \| `"N%"` | — | Position depuis le bord bas (remplace `y`) |
| `width` | px \| `"N%"` \| `"auto"` | `"100%"` | Largeur (`"auto"` = sizeHint du widget) |
| `height` | px \| `"N%"` \| `"auto"` | `"100%"` | Hauteur |
| `z_index` | int | `0` | Ordre d'empilement (plus grand = devant) |
| `margin` | px | `0` | Inset uniforme sur les 4 côtés |
| `padding` | px | `0` | Marges internes (appliquées au layout de l'enfant) |

**Exemple — caméra plein-écran avec URDF en overlay bas-gauche :**

```jsonc
{
  "type": "layout",
  "diaposition": "absolute",
  "content": [
    {
      "type": "camera",
      "name": "feed",
      "style": { "x": 0, "y": 0, "width": "100%", "height": "100%", "z_index": 0 }
    },
    {
      "type": "robot",
      "name": "overlay",
      "label": "ROBOT STATUS",
      "style": { "x": 14, "bottom": 14, "width": 320, "height": 260, "z_index": 1 }
    }
  ]
}
```

**Exemple — boutons centrés en bas :**

```jsonc
{
  "type": "button_bar",
  "name": "cam_selector",
  "style": { "x": "center", "bottom": 14, "width": "auto", "height": 40, "z_index": 1 },
  "data": { ... }
}
```

---

### chart

Graphique temps réel. Supporte 4 types.

```jsonc
{
  "type": "chart",
  "name": "mon_chart",
  "data": {
    "chart_type": "lines",   // "bar" | "band" | "pie" | "lines"
    "title": "Position Moteurs",
    "label_key": "Parameter",
    "value_key": "Value",
    "series_name": "Serie",
    "buffer_size": 50,        // lignes seulement — nombre de samples gardés
    "data": [
      { "Parameter": "FL", "Value": 0, "unit": "turns", "topic": "odrive.32.pos_estimate" },
      { "Parameter": "FR", "Value": 0, "unit": "turns", "topic": "odrive.34.pos_estimate" }
    ]
  }
}
```

| Clé | Défaut | Description |
|-----|--------|-------------|
| `chart_type` | `"bar"` | Type de graphique |
| `title` | `""` | Titre affiché |
| `label_key` | `"Parameter"` | Clé utilisée pour les étiquettes |
| `value_key` | `"Value"` | Clé utilisée pour les valeurs numériques |
| `series_name` | `"Serie 1"` | Nom de la série (pie/lines) |
| `buffer_size` | `50` | Taille du buffer circulaire (mode `lines`) |
| `data[].topic` | — | Topic EventBus → met à jour `value_key` en temps réel |

**Refresh :** 10 fps max (timer 100 ms). Met à jour uniquement si données reçues (`_dirty` flag).

---

### map

Carte interactive Leaflet.js avec tuiles satellite Esri, position robot et waypoints.

```jsonc
{
  "type": "map",
  "name": "carte",
  "data": {
    "initial_lat": 45.5048,
    "initial_lng": -73.5773,
    "initial_zoom": 17,

    "robot_position_lat_topic": "gnss.latitude",
    "robot_position_lng_topic": "gnss.longitude",
    "robot_position_yaw_topic": "gnss.yaw",

    "robot_cursor_image": "src/media/icons/robot_icons.png",
    "robot_cursor_size": [40, 40],
    "poi_image":         "src/media/icons/poi_icons.png",
    "poi_size":          [24, 32],

    "click_topic":      "map.click",       // publié au clic : {lat, lng}
    "poi_topic":        "map.poi",         // publié à l'ajout : {lat, lng, label, poi_id}
    "add_poi_at_topic": "costmap.poi",     // reçu : {lat, lng, label, poi_id, photo?}

    "local": false,
    "local_tile_url": "http://localhost:8080/tiles/{z}/{x}/{y}.png"
  }
}
```

| Comportement | Description |
|-------------|-------------|
| **Clic sur la carte** | Ajoute un waypoint `WP001`, `WP002`… avec animation flash, publie sur `click_topic` et `poi_topic` |
| **Position robot** | Marqueur mis à jour en temps réel, auto-centrage au premier fix GPS |
| **Bouton ⊕** | Recentre la vue sur la dernière position connue du robot |
| **Tuiles locales** | Si `local: true`, utilise `local_tile_url` au lieu d'Esri |

**Topics EventBus :**
- **Souscrit :** `robot_position_lat_topic`, `robot_position_lng_topic`, `robot_position_yaw_topic`, `add_poi_topic`, `add_poi_at_topic`
- **Publie :** `click_topic`, `poi_topic`, `log`

---

### bitmap

Vue bitmap (costmap) avec overlay GPS, curseur robot et picker d'altitude.

```jsonc
{
  "type": "bitmap",
  "name": "costmap",
  "data": {
    "source": "http://localhost:8080/map_feed",
    "cornerPositionWidth": 8,
    "cornerPositionHeight": 8,

    "click_topic":   "costmap.click",
    "poi_topic":     "costmap.poi",

    "gps_lat_topic": "gnss.latitude",
    "gps_lng_topic": "gnss.longitude",
    "gps_yaw_topic": "gnss.yaw",

    "robot_cursor_image": "src/media/icons/robot_icons.png",
    "robot_cursor_size":  [40, 40],
    "poi_image":          "src/media/icons/poi_icons.png",
    "poi_size":           [24, 32]
  }
}
```

**Comportement :** Polling HTTP de l'image source. Clic sur l'image → dialog picker d'altitude (OCR optionnel) → publie un POI avec coordonnées GPS interpolées.

---

### camera

Widget caméra unifié — switche entre RTSP et webcam, supporte plusieurs sources.

```jsonc
{
  "type": "camera",
  "name": "Camera",
  "data": {
    "mode": "rtsp",              // mode initial : "rtsp" | "webcamera"
    "hide_controls": false,      // cache la sidebar de sélection
    "select_topic": "camera.select",  // reçoit un nom de caméra pour sélection externe

    "vtx_host": "192.168.2.2",
    "vtx_port": 5540,

    "cameras": [
      { "name": "REAR_CAM", "udp_vtx_id": 0, "rtsp_ip": "192.168.2.30" },
      { "name": "ARM_CAM",  "udp_vtx_id": 4, "rtsp_ip": "192.168.2.34" }
    ],

    "rtsp": {
      "source": "rtsp://192.168.2.30:554/",
      "source_type": "rtsp"
    },
    "webcamera": {
      "device_path": "/dev/video0",
      "responsive": { "aspect_ratio": "4:3", "overflow_anchor": "center" }
    }
  }
}
```

| Clé | Défaut | Description |
|-----|--------|-------------|
| `mode` | `"rtsp"` | Mode d'affichage initial |
| `hide_controls` | `false` | Cache la sidebar (mais garde le ping de fallback) |
| `select_topic` | — | Topic EventBus → sélectionne la caméra par `name` |
| `cameras` | `[]` | Liste des caméras disponibles (≥ 2 = mode multi-caméra) |
| `vtx_host/port` | `192.168.2.2:5540` | Commandes de switchover VTX |

**Comportement :** Ping RTSP toutes les 5 s. Si RTSP devient injoignable → bascule automatiquement en WebCamera. Le `select_topic` reçoit une chaîne avec le `name` de la caméra (ex: `"REAR_CAM"`).

---

### robot

Visualiseur URDF 3D (Three.js) avec mise à jour en temps réel des angles de joints, de la pose et des couleurs thermiques.

```jsonc
{
  "type": "robot",
  "name": "Rove3D",
  "data": {
    "urdf": "src/media/rove_urdf/rove.urdf",
    "hide_joint_panel": false,    // cache le panneau des joints

    "link_colors": {
      "Core": "#c8c8d0",
      "DrumFL": "#5aab5a"
    },

    "controls": {
      "joint_angles": [
        {
          "joint":  "joint_revolute_9",
          "topic":  "kinova_arm.joint_1_pos",
          "scale":  0.01745,   // facteur : 0.01745 = degrés→radians
          "offset": 1.5708
        }
      ],

      "robot_pose": {
        "roll_topic":  "gnss.roll",
        "pitch_topic": "gnss.pitch",
        "yaw_topic":   "gnss.yaw"
      },

      "thermal_links": [
        {
          "link":     "DrumFL",
          "topic":    "odrive.32.motor_temp",
          "min_temp": 20,
          "max_temp": 80
        }
      ]
    }
  }
}
```

| Clé | Description |
|-----|-------------|
| `urdf` | Chemin relatif (depuis la racine du projet) ou absolu vers le `.urdf` |
| `hide_joint_panel` | Cache l'UI de debug des joints |
| `link_colors` | Couleurs statiques par lien URDF |
| `controls.joint_angles` | Angle du joint = `valeur_reçue × scale + offset` (radians) |
| `controls.robot_pose` | Roll/Pitch/Yaw en degrés → convertis en radians automatiquement |
| `controls.thermal_links` | Gradient de couleur froid→chaud sur les liens + barre de progression |

**Gradient thermique :** `min_temp` → bleu `#1a6fff` · 35% → vert `#00e676` · 65% → ambre `#ffb300` · `max_temp` → rouge `#ff3d3d`.

---

### button_bar

Barre de boutons qui publient des événements sur l'EventBus.

```jsonc
{
  "type": "button_bar",
  "name": "cam_selector",
  "data": {
    "orientation": "horizontal",   // "horizontal" | "vertical"
    "label": "CAMERAS",            // texte dim affiché avant les boutons
    "height": 44,                  // hauteur fixe en px

    "buttons": [
      {
        "label":        "REAR CAM",
        "event":        "camera.select",   // topic publié au clic
        "value":        "REAR_CAM",        // valeur envoyée avec l'event
        "active_topic": "camera.select"    // topic pour synchroniser l'état actif
      }
    ]
  }
}
```

Le bouton se surligne (bordure orange) quand `active_topic` reçoit sa `value`. Peut être utilisé comme composant inline dans un layout ou comme `bottom_bar` au niveau fenêtre.

**`bottom_bar` (niveau fenêtre) :**

```jsonc
{
  "bottom_bar": {
    "label": "CAMERAS",
    "buttons": [ ... ]
  }
}
```

---

### console

Console de logs EventBus. Affiche tous les messages publiés sur le topic `log`.

```jsonc
{
  "type": "console",
  "name": "event_log"
}
```

Format d'affichage : `[HH:MM:SS.mmm]  message` — timestamp en orange, message en blanc.

---

### table

Tableau de données statiques ou configurées.

```jsonc
{
  "type": "table",
  "name": "telemetry",
  "data": {
    "header": ["Paramètre", "Valeur", "Unité"],
    "data": [
      { "Paramètre": "Tension", "Valeur": "24.6", "Unité": "V" },
      { "Paramètre": "Courant", "Valeur": "3.2",  "Unité": "A" }
    ]
  }
}
```

---

### rtsp / webcamera

Composants de bas niveau utilisés en interne par `camera`. Peuvent être utilisés directement pour des cas simples (source unique fixe).

```jsonc
{ "type": "rtsp",      "name": "cam", "data": { "source": "rtsp://192.168.2.30:554/" } }
{ "type": "webcamera", "name": "cam", "data": { "device_path": "/dev/video0" } }
```

---

### threejsviewer

Viewer Three.js générique pour scènes 3D personnalisées.

```jsonc
{
  "type": "threejsviewer",
  "name": "scene3d",
  "data": { ... },
  "controls": { ... }
}
```

---

## EventBus

Le `EventBus` est un singleton pub/sub qui découple tous les composants.

```python
event_bus.subscribe("gnss.latitude", callback)  # s'abonner
event_bus.publish_sync("log", "message")         # publier (synchrone)
await event_bus.publish("log", "message")        # publier (async)
```

**Topics standards utilisés dans les configs :**

| Topic | Produit par | Consommé par |
|-------|------------|--------------|
| `log` | tous | `console` |
| `gnss.latitude` | UDP client vn300 | `map`, `bitmap`, `robot` |
| `gnss.longitude` | UDP client vn300 | `map`, `bitmap`, `robot` |
| `gnss.yaw` | UDP client vn300 | `map`, `bitmap`, `robot` |
| `gnss.roll/pitch` | UDP client vn300 | `robot` |
| `odrive.32.pos_estimate` | UDP client odrive_32 | `chart` |
| `odrive.32.motor_temp` | UDP client odrive_32 | `chart`, `robot` (thermal) |
| `camera.select` | `button_bar` | `camera` |
| `costmap.poi` | `bitmap` | `map` (via `add_poi_at_topic`) |
| `battery.percentage` | UDP client | `header` |
| `estop_status` | UDP client | `header` |

---

## Thème

Toutes les constantes visuelles sont centralisées dans [`src/views/theme.py`](src/views/theme.py).

| Constante | Valeur | Usage |
|-----------|--------|-------|
| `BG_DEEP` | `#080808` | Fond fenêtre |
| `BG_DARK` | `#0f0f0f` | Fond panel |
| `BG_PANEL` | `#161616` | Surfaces élevées |
| `BG_SURFACE` | `#1e1e1e` | Éléments interactifs |
| `BORDER` | `#2e2e2e` | Bordures standard |
| `CYAN` | `#ffae00` | Accent principal (orange) |
| `GREEN` | `#00e676` | OK / connecté |
| `RED` | `#ff3d3d` | Alerte / erreur |
| `AMBER` | `#ffb300` | Avertissement |
| `TEXT` | `#d0d8e0` | Texte principal |
| `TEXT_DIM` | `#505050` | Texte secondaire |
| `FONT_MONO` | `Courier New` | Police globale |

`theme.GLOBAL` est appliqué sur le `QApplication` au démarrage — il couvre font, couleurs QLabel/QComboBox, scrollbars, et tooltips.

---

## Dépannage

**Carte vide (fond noir) :** Leaflet est bundlé localement (`src/views/components/html/leaflet.min.js`). Si les tuiles satellite ne chargent pas, configurer un serveur local avec `"local": true` dans le config map.

**Caméra RTSP absente :** Vérifier que `rtsp_ip` est joignable et que GStreamer est installé (`gstreamer1.0-plugins-bad` pour H264).

**Fenêtres non-plein-écran :** `showFullScreen()` utilisé par défaut. Sur WSL, vérifier que WSLg est actif (`echo $WAYLAND_DISPLAY`).

**EventBus inter-fenêtres :** Les deux fenêtres partagent le même `EventBus` (passé par référence depuis `widget.py`). Les topics publiés par window 1 (ex: `camera.select`) sont reçus par window 2.

---

## Build Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
./build_windows.ps1 -Mode onedir
```

Binaire dans `dist\capraui\`.
