# Exemple de configuration CAPRA_UI

Ce fichier montre un exemple de configuration complète pour CAPRA_UI.

## Utilisation

Copiez `config_default.json` vers :
```bash
mkdir -p ~/.config/CAPRA_UI
cp config_default.json ~/.config/CAPRA_UI/capra_ui_config.json
```

Puis modifiez selon vos besoins.

## Exemples de configurations

### Configuration minimaliste (mode standalone)
```json
{
    "general": {
        "auto_connect": true,
        "refresh_rate": 30
    },
    "map": {
        "latitude": 45.5017,
        "longitude": -73.5673,
        "zoom": 13
    },
    "panels": [
        {
            "type": "map",
            "title": "Carte",
            "enabled": true
        }
    ],
    "rtsp_streams": []
}
```

### Configuration avec une caméra
```json
{
    "general": {
        "auto_connect": true
    },
    "rtsp_streams": [
        {
            "name": "Caméra Principale",
            "url": "rtsp://admin:123456@192.168.168.115:554/stream1",
            "enabled": true
        }
    ],
    "panels": [
        {
            "type": "map",
            "title": "Carte",
            "enabled": true
        },
        {
            "type": "rtsp",
            "title": "Caméra",
            "properties": {"stream_index": 0},
            "enabled": true
        }
    ]
}
```

### Configuration multi-caméras
```json
{
    "rtsp_streams": [
        {
            "name": "Avant",
            "url": "rtsp://192.168.1.100:554/stream1",
            "enabled": true
        },
        {
            "name": "Arrière",
            "url": "rtsp://192.168.1.101:554/stream1",
            "enabled": true
        },
        {
            "name": "Gauche",
            "url": "rtsp://192.168.1.102:554/stream1",
            "enabled": true
        }
    ],
    "panels": [
        {"type": "rtsp", "properties": {"stream_index": 0}},
        {"type": "rtsp", "properties": {"stream_index": 1}},
        {"type": "rtsp", "properties": {"stream_index": 2}}
    ]
}
```

## Champs disponibles

### general
- `auto_connect` (bool): Connexion automatique au démarrage
- `language` (string): Code langue (fr_CA, en_US, etc.)
- `refresh_rate` (int): FPS de rafraîchissement (10-60)

### map
- `latitude` (float): Latitude initiale
- `longitude` (float): Longitude initiale
- `zoom` (int): Niveau de zoom (1-20)
- `type` (string): "satellite", "street", "hybrid", "terrain"

### rtsp_streams (array)
Chaque stream contient :
- `name` (string): Nom descriptif
- `url` (string): URL RTSP complète (rtsp://user:pass@ip:port/path)
- `enabled` (bool): Activer ce stream

### panels (array)
Chaque panel contient :
- `type` (string): "map", "rtsp", "pointcloud"
- `title` (string): Titre affiché
- `enabled` (bool): Afficher ce panel
- `properties` (object): Propriétés spécifiques au type
  - Pour RTSP: `{"stream_index": 0}` (index dans rtsp_streams)

### ros_topics (mode ROS 2 uniquement)
- `pointcloud` (string): Topic des nuages de points
- `pose` (string): Topic de la position du robot
- `image` (string): Topic des images
