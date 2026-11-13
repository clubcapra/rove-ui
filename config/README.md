# Configuration — Guide de référence

Toutes les interfaces sont définies par des fichiers JSON dans ce dossier.  
Aucune modification de code nécessaire pour changer la disposition, ajouter un composant ou modifier les sources de données.

---

## Structure d'un fichier de config

```jsonc
{
  // ── Barre de statut (haut) ──────────────────────────────────────────
  "header_settings": { ... },

  // ── Clients de données ──────────────────────────────────────────────
  "udp_clients": [ ... ],
  "ros2_clients": [ ... ],

  // ── Barre d'actions persistante (bas de la fenêtre, optionnel) ──────
  "bottom_bar": { ... },

  // ── Vues (onglets de navigation) ────────────────────────────────────
  "views": {
    "NOM_ONGLET": { "type": "layout", ... },
    "AUTRE_ONGLET": { "type": "layout", ... }
  }
}
```

> **Note :** Si une seule vue est définie, la barre de navigation est automatiquement cachée.

---

## Système de layouts

### `"horizontal"` (défaut)

Les enfants sont placés côte à côte et s'étirent pour remplir la hauteur.

```jsonc
{
  "type": "layout",
  "diaposition": "horizontal",
  "content": [
    { "type": "chart", "name": "chart_gauche", "data": { ... } },
    { "type": "chart", "name": "chart_droite", "data": { ... } }
  ]
}
```

---

### `"vertical"`

Les enfants sont empilés de haut en bas.

```jsonc
{
  "type": "layout",
  "diaposition": "vertical",
  "content": [
    { "type": "camera", "name": "feed",  "data": { ... } },
    { "type": "console", "name": "logs" }
  ]
}
```

---

### `"grid"`

Grille de cellules. Chaque enfant peut spécifier sa position et son span via la clé `"grid"`.

```jsonc
{
  "type": "layout",
  "diaposition": "grid",
  "grid": {
    "rows":    3,
    "columns": 2,
    "spacing": 6
  },
  "content": [
    {
      "type": "chart", "name": "A",
      "grid": { "row": 0, "column": 0 }
    },
    {
      "type": "chart", "name": "B",
      "grid": { "row": 0, "column": 1 }
    },
    {
      "type": "bitmap", "name": "C",
      "grid": { "row": 1, "column": 1, "row_span": 2, "column_span": 1 }
    }
  ]
}
```

**Clés `"grid"` par enfant :**

| Clé | Défaut | Description |
|-----|--------|-------------|
| `row` | auto | Ligne (0-indexé) |
| `column` | auto | Colonne (0-indexé) |
| `row_span` | `1` | Nombre de lignes occupées |
| `column_span` | `1` | Nombre de colonnes occupées |

**Visualisation d'une grille 3×2 :**

```
col →    0          1
row ↓ ┌──────────┬──────────┐
  0   │  chart A │  chart B │
      ├──────────┼──────────┤
  1   │  chart C │          │
      ├──────────┤  bitmap  │
  2   │  robot   │          │
      └──────────┴──────────┘
```

---

### `"absolute"`

Positionnement libre avec superposition de couches (`z_index`). Indispensable pour les overlays.

```jsonc
{
  "type": "layout",
  "diaposition": "absolute",
  "content": [
    {
      "type": "map",
      "name": "carte",
      "style": { "x": 0, "y": 0, "width": "100%", "height": "100%", "z_index": 0 },
      "data": { ... }
    },
    {
      "type": "button_bar",
      "name": "boutons_cam",
      "style": { "x": "center", "bottom": 14, "width": "auto", "height": 40, "z_index": 1 },
      "data": { ... }
    },
    {
      "type": "robot",
      "name": "urdf_overlay",
      "label": "ROBOT STATUS",
      "style": { "x": 14, "bottom": 14, "width": 320, "height": 260, "z_index": 2 },
      "data": { ... }
    }
  ]
}
```

**Référence complète des propriétés `"style"` :**

| Propriété | Valeurs | Défaut | Description |
|-----------|---------|--------|-------------|
| `x` | px, `"N%"`, `"center"` | `0` | Position depuis le bord gauche. `"center"` centre horizontalement. |
| `y` | px, `"N%"`, `"center"` | `0` | Position depuis le bord haut. `"center"` centre verticalement. |
| `right` | px, `"N%"` | — | Position depuis le bord **droit** (remplace `x`) |
| `bottom` | px, `"N%"` | — | Position depuis le bord **bas** (remplace `y`) |
| `width` | px, `"N%"`, `"auto"` | `"100%"` | Largeur. `"auto"` = taille naturelle du widget. |
| `height` | px, `"N%"`, `"auto"` | `"100%"` | Hauteur. `"auto"` = taille naturelle du widget. |
| `z_index` | entier | `0` | Ordre d'empilement. Valeur plus haute = devant. |
| `margin` | px | `0` | Inset uniforme sur les 4 côtés (réduit taille et décale position). |
| `padding` | px | `0` | Marges internes appliquées au layout de l'enfant. |

**Exemples de positionnement :**

```jsonc
// Centre exact
"style": { "x": "center", "y": "center", "width": 400, "height": 300 }

// Coin haut-droite, marge de 12px
"style": { "right": 12, "y": 12, "width": 200, "height": 44, "z_index": 1 }

// Bas-gauche, largeur auto
"style": { "x": 14, "bottom": 14, "width": "auto", "height": 44 }

// Bande du bas, pleine largeur
"style": { "x": 0, "bottom": 0, "width": "100%", "height": 50 }

// Moitié droite, pleine hauteur
"style": { "x": "50%", "y": 0, "width": "50%", "height": "100%" }
```

---

### Layouts imbriqués

Un composant de type `"layout"` peut être enfant d'un autre layout, permettant de combiner les modes.

```jsonc
{
  "type": "layout",
  "diaposition": "absolute",
  "content": [
    {
      "type": "map",
      "name": "fond_carte",
      "style": { "x": 0, "y": 0, "width": "100%", "height": "100%" }
    },
    {
      "type": "layout",
      "name": "hud_droite",
      "diaposition": "vertical",
      "style": { "right": 12, "y": 12, "width": 280, "height": "60%", "z_index": 1 },
      "content": [
        { "type": "chart", "name": "vitesse", "data": { ... } },
        { "type": "chart", "name": "temp",    "data": { ... } }
      ]
    }
  ]
}
```

---

### Label de panel

N'importe quel composant peut recevoir une clé `"label"` pour afficher une barre-titre tactique.

```jsonc
{
  "type": "chart",
  "name": "motor_temps",
  "label": "TEMPÉRATURES MOTEURS",
  "data": { ... }
}
```

---

### Héritage de données

La clé `"data"` d'un layout est fusionnée (merge profond) dans les `"data"` de ses enfants.

```jsonc
{
  "type": "layout",
  "diaposition": "grid",
  "data": {
    "vtx_host": "192.168.2.2",
    "vtx_port": 5540
  },
  "content": [
    {
      "type": "camera",
      "name": "cam1",
      "data": { "mode": "rtsp" }
    }
  ]
}
```

---

## Référence des widgets

---

### `chart` — Graphique temps réel

```jsonc
{
  "type": "chart",
  "name": "position_moteurs",
  "label": "POSITION MOTEURS",
  "data": {
    "chart_type":  "lines",
    "title":       "Position Moteurs",
    "label_key":   "Parameter",
    "value_key":   "Value",
    "series_name": "Position",
    "buffer_size": 50,
    "data": [
      { "Parameter": "FL", "Value": 0, "unit": "turns", "topic": "odrive.32.pos_estimate" },
      { "Parameter": "RL", "Value": 0, "unit": "turns", "topic": "odrive.33.pos_estimate" },
      { "Parameter": "FR", "Value": 0, "unit": "turns", "topic": "odrive.34.pos_estimate" },
      { "Parameter": "RR", "Value": 0, "unit": "turns", "topic": "odrive.31.pos_estimate" }
    ]
  }
}
```

| Option | Valeurs | Défaut | Description |
|--------|---------|--------|-------------|
| `chart_type` | `"bar"` `"band"` `"pie"` `"lines"` | `"bar"` | Type. `"band"` = barres horizontales. `"lines"` = courbes avec buffer. |
| `title` | string | `""` | Titre affiché |
| `label_key` | string | `"Parameter"` | Clé pour les étiquettes dans `data[]` |
| `value_key` | string | `"Value"` | Clé pour les valeurs numériques dans `data[]` |
| `series_name` | string | `"Serie 1"` | Nom de la série (pie, lines) |
| `buffer_size` | entier | `50` | Taille du buffer circulaire (mode `"lines"` uniquement) |
| `data[].topic` | string | — | Topic EventBus → met à jour la valeur en temps réel |
| `data[].unit` | string | — | Unité affichée |

---

### `map` — Carte interactive satellite

```jsonc
{
  "type": "map",
  "name": "carte_gps",
  "label": "MISSION MAP",
  "data": {
    "initial_lat":  45.5048,
    "initial_lng":  -73.5773,
    "initial_zoom": 17,

    "robot_position_lat_topic": "gnss.latitude",
    "robot_position_lng_topic": "gnss.longitude",
    "robot_position_yaw_topic": "gnss.yaw",

    "robot_cursor_image": "src/media/icons/robot_icons.png",
    "robot_cursor_size":  [40, 40],
    "poi_image":          "src/media/icons/poi_icons.png",
    "poi_size":           [24, 32],

    "click_topic":      "map.click",
    "poi_topic":        "map.poi",
    "add_poi_at_topic": "costmap.poi",

    "local":          false,
    "local_tile_url": "http://localhost:8080/tiles/{z}/{x}/{y}.png"
  }
}
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `initial_lat` / `initial_lng` | `45.5048` / `-73.5773` | Centre initial de la carte |
| `initial_zoom` | `15` | Zoom initial (1=monde, 19=bâtiment) |
| `robot_position_lat_topic` | — | Topic → latitude (float) |
| `robot_position_lng_topic` | — | Topic → longitude (float) |
| `robot_position_yaw_topic` | — | Topic → cap en degrés |
| `robot_cursor_image` | — | Image du marqueur robot (chemin relatif au projet) |
| `robot_cursor_size` | `[36,36]` | Dimensions du marqueur robot `[w, h]` |
| `poi_image` | — | Image des waypoints |
| `poi_size` | `[24,32]` | Dimensions des waypoints `[w, h]` |
| `click_topic` | — | **Publié** au clic : `{"lat": ..., "lng": ...}` |
| `poi_topic` | — | **Publié** à l'ajout : `{"lat", "lng", "label", "poi_id"}` |
| `add_poi_at_topic` | — | **Reçu** : ajoute un POI `{"lat", "lng", "label", "poi_id", "photo?"}` |
| `local` | `false` | Si `true`, charge les tuiles depuis `local_tile_url` |
| `local_tile_url` | `localhost:8080/tiles/...` | Serveur de tuiles local |

**Comportement :** Clic sur la carte → waypoint `WP001`, `WP002`… | Bouton **⊕** → recentre sur le robot | Premier fix GPS → auto-centrage.

---

### `bitmap` — Costmap / image aérienne

```jsonc
{
  "type": "bitmap",
  "name": "costmap",
  "label": "COSTMAP",
  "data": {
    "source": "http://localhost:8080/map_feed",
    "cornerPositionWidth":  8,
    "cornerPositionHeight": 8,

    "click_topic": "costmap.click",
    "poi_topic":   "costmap.poi",

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

| Option | Défaut | Description |
|--------|--------|-------------|
| `source` | — | URL HTTP de l'image (polling continu ~200 ms) |
| `cornerPositionWidth/Height` | `8` | Zone de détection des coins en % |
| `click_topic` | — | **Publié** au clic : position normalisée `{nx, ny}` |
| `poi_topic` | — | **Publié** après validation : `{lat, lng, altitude, label, poi_id}` |
| `gps_*_topic` | — | Topics GPS pour le curseur robot et le calcul de position |

---

### `camera` — Caméra RTSP / Webcam

```jsonc
{
  "type": "camera",
  "name": "Camera",
  "data": {
    "mode": "rtsp",

    "hide_controls": false,
    "select_topic":  "camera.select",

    "vtx_host": "192.168.2.2",
    "vtx_port": 5540,

    "cameras": [
      { "name": "REAR_CAM", "udp_vtx_id": 0, "rtsp_ip": "192.168.2.30" },
      { "name": "ARM_CAM",  "udp_vtx_id": 4, "rtsp_ip": "192.168.2.34" }
    ],

    "rtsp":      { "source": "rtsp://192.168.2.30:554/", "source_type": "rtsp" },
    "webcamera": {
      "device_path": "/dev/video0",
      "responsive":  { "aspect_ratio": "4:3", "overflow_anchor": "center" }
    }
  }
}
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `mode` | `"rtsp"` | Mode initial : `"rtsp"` ou `"webcamera"` |
| `hide_controls` | `false` | Cache la sidebar de sélection (garder pour les overlays fullscreen) |
| `select_topic` | — | **Reçu** : chaîne avec le `name` de la caméra à activer |
| `cameras` | `[]` | Si ≥ 2 entrées : mode multi-caméra avec sidebar et ping |
| `cameras[].name` | — | Identifiant unique, valeur attendue sur `select_topic` |
| `cameras[].udp_vtx_id` | — | ID VTX pour le switchover hardware |
| `cameras[].rtsp_ip` | — | IP de la source RTSP (`rtsp://{ip}:554/` auto-généré) |
| `cameras[].rtsp_source` | auto | URL RTSP complète (surcharge l'auto-génération) |
| `vtx_host` / `vtx_port` | `192.168.2.2:5540` | Adresse pour les commandes VTX |

**Fallback automatique :** Ping RTSP toutes les 5 s → bascule en `webcamera` si inaccessible.

---

### `robot` — Visualiseur URDF 3D

```jsonc
{
  "type": "robot",
  "name": "Rove3D",
  "label": "3D VIEWER",
  "data": {
    "urdf": "src/media/rove_urdf/rove.urdf",
    "hide_joint_panel": false,

    "link_colors": {
      "Core":      "#c8c8d0",
      "FlipperFL": "#72c572",
      "DrumFL":    "#5aab5a"
    },

    "controls": {

      "joint_angles": [
        {
          "joint":  "joint_revolute_9",
          "topic":  "kinova_arm.joint_1_pos",
          "scale":  0.01745,
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

| Option | Défaut | Description |
|--------|--------|-------------|
| `urdf` | — | Chemin vers le `.urdf` (relatif à la racine du projet) |
| `hide_joint_panel` | `false` | Cache le panneau de debug des joints |
| `link_colors` | `{}` | Couleurs statiques par pièce URDF `{"NomPiece": "#hex"}` |
| `controls.joint_angles[].joint` | — | Nom du joint dans le URDF |
| `controls.joint_angles[].topic` | — | Topic → valeur de l'angle |
| `controls.joint_angles[].scale` | `1.0` | Multiplicateur. `0.01745` = degrés→radians |
| `controls.joint_angles[].offset` | `0.0` | Décalage additif en radians |
| `controls.robot_pose.roll/pitch/yaw_topic` | — | Orientation du robot (degrés → radians auto) |
| `controls.thermal_links[].link` | — | Pièce URDF à colorier thermiquement |
| `controls.thermal_links[].topic` | — | Topic de température en °C |
| `controls.thermal_links[].min_temp` | `20.0` | Température = couleur froide (bleu) |
| `controls.thermal_links[].max_temp` | `80.0` | Température = couleur chaude (rouge) |

**Gradient thermique :**
```
min_temp ───── 35% ───── 65% ───── max_temp
  bleu          vert     ambre       rouge
 #1a6fff       #00e676  #ffb300    #ff3d3d
```
Une barre de progression s'affiche automatiquement sous le viewer pour chaque `thermal_link`.

---

### `button_bar` — Barre de boutons

```jsonc
{
  "type": "button_bar",
  "name": "cam_controls",
  "data": {
    "orientation": "horizontal",
    "label":       "CAMERAS",
    "height":      44,
    "buttons": [
      {
        "label":        "REAR CAM",
        "event":        "camera.select",
        "value":        "REAR_CAM",
        "active_topic": "camera.select"
      },
      {
        "label":        "ARM CAM",
        "event":        "camera.select",
        "value":        "ARM_CAM",
        "active_topic": "camera.select"
      }
    ]
  }
}
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `orientation` | `"horizontal"` | `"horizontal"` ou `"vertical"` |
| `label` | — | Texte dim affiché avant les boutons |
| `height` | `44` | Hauteur en px (ignorée si utilisé en layout `absolute`) |
| `buttons[].label` | — | Texte du bouton |
| `buttons[].event` | — | Topic EventBus **publié** au clic |
| `buttons[].value` | — | Valeur envoyée avec l'event |
| `buttons[].active_topic` | — | Topic **reçu** → surligne le bouton si la valeur correspond |

Peut aussi être déclaré au niveau fenêtre via `"bottom_bar"` (persistent sur tous les onglets) :

```jsonc
{
  "bottom_bar": {
    "label": "CAMERAS",
    "buttons": [ ... ]
  },
  "views": { ... }
}
```

---

### `console` — Journal d'événements

```jsonc
{
  "type": "console",
  "name": "event_log"
}
```

Aucune option. Affiche tous les messages du topic `log` avec timestamp orange.

---

### `table` — Tableau de données

```jsonc
{
  "type": "table",
  "name": "telemetry",
  "label": "TÉLÉMÉTRIE",
  "data": {
    "header": ["Paramètre", "Valeur", "Unité"],
    "data": [
      { "Paramètre": "Tension", "Valeur": "24.6", "Unité": "V"   },
      { "Paramètre": "Courant", "Valeur": "3.2",  "Unité": "A"   },
      { "Paramètre": "Vitesse", "Valeur": "1.4",  "Unité": "m/s" }
    ]
  }
}
```

---

### `rtsp` — Flux RTSP direct

```jsonc
{
  "type": "rtsp",
  "name": "camera_avant",
  "data": {
    "source":      "rtsp://192.168.2.30:554/",
    "source_type": "rtsp"
  }
}
```

---

### `webcamera` — Webcam USB directe

```jsonc
{
  "type": "webcamera",
  "name": "vtx_feed",
  "data": {
    "device_path": "/dev/video0",
    "responsive": {
      "aspect_ratio":    "4:3",
      "overflow_anchor": "center"
    }
  }
}
```

---

## Header

```jsonc
"header_settings": {
  "signals": [
    { "name": "MicroHard", "host": "192.168.2.10" }
  ],
  "ping_interval_s": 2,
  "battery_topic":   "battery.voltage",
  "E-Stop": {
    "active_color":   "#ff3d3d",
    "inactive_color": "#00e676",
    "topic":          "estop_status"
  }
}
```

| Option | Description |
|--------|-------------|
| `signals` | Liste de signaux à pinger. Affiché : `[LINK nom Xms]` en vert/ambre/rouge. |
| `ping_interval_s` | Intervalle de ping en secondes |
| `battery_topic` | Topic → valeur affichée comme `🔋 24.6V` |
| `E-Stop.topic` | Topic `bool` → `[E-STOP NOMINAL]` vert ou `[E-STOP ACTIVE]` fond rouge |

---

## Clients UDP

```jsonc
"udp_clients": [
  {
    "type":                   "udp_poll",
    "name":                   "odrive_32",
    "base_url":               "http://192.168.2.2:8080",
    "discovery_endpoint":     "/discover",
    "discovery_sensor_id":    "odrive_32",
    "discovery_port_field":   "data_port",
    "topic":                  "odrive.32",
    "topic_prefix":           "odrive.32",
    "proto_type":             "DriveNodeState",
    "publish_field_topics":   true,
    "poll_interval_ms":       100,
    "recv_timeout_s":         2.0,
    "rediscovery_interval_s": 30,
    "enabled":                true
  }
]
```

Avec `publish_field_topics: true`, chaque champ du proto génère un topic `{prefix}.{champ}` :  
ex. `odrive.32.pos_estimate`, `odrive.32.motor_temp`, `odrive.32.fet_temp`.

---

## Exemples complets

### Vue MISSION — carte plein écran avec boutons flottants

```jsonc
"MISSION": {
  "type": "layout",
  "diaposition": "absolute",
  "content": [
    {
      "type": "map", "name": "carte",
      "style": { "x": 0, "y": 0, "width": "100%", "height": "100%", "z_index": 0 },
      "data": {
        "initial_lat": 45.5048, "initial_lng": -73.5773, "initial_zoom": 17,
        "robot_position_lat_topic": "gnss.latitude",
        "robot_position_lng_topic": "gnss.longitude",
        "robot_position_yaw_topic": "gnss.yaw",
        "click_topic": "map.click", "poi_topic": "map.poi",
        "add_poi_at_topic": "costmap.poi"
      }
    },
    {
      "type": "button_bar", "name": "cam_selector",
      "style": { "x": "center", "bottom": 14, "width": "auto", "height": 40, "z_index": 1 },
      "data": {
        "height": 40,
        "buttons": [
          { "label": "REAR CAM", "event": "camera.select", "value": "REAR_CAM", "active_topic": "camera.select" },
          { "label": "ARM CAM",  "event": "camera.select", "value": "ARM_CAM",  "active_topic": "camera.select" }
        ]
      }
    }
  ]
}
```

### Vue TELEMETRY — grille 2×2 avec labels

```jsonc
"TELEMETRY": {
  "type": "layout",
  "diaposition": "grid",
  "grid": { "rows": 2, "columns": 2, "spacing": 6 },
  "content": [
    {
      "type": "chart", "name": "pos_moteurs", "label": "POSITION MOTEURS",
      "grid": { "row": 0, "column": 0 },
      "data": {
        "chart_type": "lines", "title": "Position",
        "data": [
          { "Parameter": "FL", "Value": 0, "topic": "odrive.32.pos_estimate" },
          { "Parameter": "FR", "Value": 0, "topic": "odrive.34.pos_estimate" }
        ]
      }
    },
    {
      "type": "chart", "name": "temp_moteurs", "label": "TEMP. MOTEURS",
      "grid": { "row": 0, "column": 1 },
      "data": {
        "chart_type": "band", "title": "Températures",
        "data": [
          { "Parameter": "FL", "Value": 0, "unit": "°C", "topic": "odrive.32.motor_temp" },
          { "Parameter": "FR", "Value": 0, "unit": "°C", "topic": "odrive.34.motor_temp" }
        ]
      }
    },
    {
      "type": "chart", "name": "temp_drivers", "label": "TEMP. DRIVERS",
      "grid": { "row": 1, "column": 0 },
      "data": {
        "chart_type": "band", "title": "Drivers",
        "data": [
          { "Parameter": "FL", "Value": 0, "unit": "°C", "topic": "odrive.32.fet_temp" },
          { "Parameter": "FR", "Value": 0, "unit": "°C", "topic": "odrive.34.fet_temp" }
        ]
      }
    },
    {
      "type": "robot", "name": "rove3d", "label": "3D VIEWER",
      "grid": { "row": 1, "column": 1 },
      "data": {
        "urdf": "src/media/rove_urdf/rove.urdf",
        "controls": {
          "robot_pose": { "roll_topic": "gnss.roll", "pitch_topic": "gnss.pitch", "yaw_topic": "gnss.yaw" }
        }
      }
    }
  ]
}
```

### Vue CAMERA — caméra fullscreen + URDF thermique overlay

```jsonc
"CAMERA": {
  "type": "layout",
  "diaposition": "absolute",
  "content": [
    {
      "type": "camera", "name": "feed",
      "style": { "x": 0, "y": 0, "width": "100%", "height": "100%", "z_index": 0 },
      "data": {
        "mode": "rtsp",
        "hide_controls": true,
        "select_topic":  "camera.select",
        "cameras": [
          { "name": "REAR_CAM", "udp_vtx_id": 0, "rtsp_ip": "192.168.2.30" },
          { "name": "ARM_CAM",  "udp_vtx_id": 4, "rtsp_ip": "192.168.2.34" }
        ],
        "rtsp":      { "source": "rtsp://192.168.2.30:554/" },
        "webcamera": { "device_path": "/dev/video0" }
      }
    },
    {
      "type": "robot", "name": "urdf_overlay", "label": "ROBOT STATUS",
      "style": { "x": 14, "bottom": 14, "width": 320, "height": 260, "z_index": 1 },
      "data": {
        "urdf": "src/media/rove_urdf/rove.urdf",
        "hide_joint_panel": true,
        "controls": {
          "thermal_links": [
            { "link": "DrumFL", "topic": "odrive.32.motor_temp", "min_temp": 20, "max_temp": 80 },
            { "link": "DrumBL", "topic": "odrive.33.motor_temp", "min_temp": 20, "max_temp": 80 },
            { "link": "DrumFR", "topic": "odrive.34.motor_temp", "min_temp": 20, "max_temp": 80 },
            { "link": "DrumBR", "topic": "odrive.31.motor_temp", "min_temp": 20, "max_temp": 80 }
          ],
          "robot_pose": { "roll_topic": "gnss.roll", "pitch_topic": "gnss.pitch", "yaw_topic": "gnss.yaw" }
        }
      }
    }
  ]
}
```
