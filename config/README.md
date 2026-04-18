
## RTSP - Widget

``` JSON
{
    "type": "rtsp",
    "name": "RTSP Camera",
    "data": {
        "source": "rtsp://192.168.2.34:554/",
        "autoplay": true,
        "backend": "mpv",
        "rtsp_transport": "udp",
        "no_audio": true,
        "mpv_untimed": true,
        "display_fps_override": 15,
        "demuxer_max_bytes": "500k",
        "demuxer_readahead_secs": 0,
        "mpv_vd_lavc_threads": 4,
        "audio_volume": 0.0,
        "probe_size": 65536,
        "network_timeout_ms": 3000
    },
    "grid": {
    "row": 0,
    "column": 1,
    "row_span": 1,
    "column_span": 1
    }
},
```

## WebCamera - Widget
``` JSON
{
    "type": "webcamera",
    "name": "webcamera",
    "data": {
        "device_path": "/dev/video0"
    },
    "grid": {
    "row": 0,
    "column": 1,
    "row_span": 1,
    "column_span": 1
    }
}
```

## Table - Widget

```JSON

{
    "type": "table",
    "name": "Temperature",
    "data": {
        "header": ["Parameter", "Value"],
        "data": [
        {"Parameter": "Odrive 1", "Value": 35, "unit": "°C"
        },
        {
            "Parameter": "Odrive 2", "Value": 45, "unit": "°C"
        },
        {
            "Parameter": "Odrive 3", "Value": 45, "unit": "°C"
        }  ,
        {
            "Parameter": "Odrive 4", "Value": 45, "unit": "°C"
        }        
        ]
    },
    "grid": {
    "row": 0,
    "column": 1,
    "row_span": 1,
    "column_span": 1
    }
},
```


## Diagramme - Widget

``` JSON
{
    "type": "chart",
    "name": "Temperature",
    "data": {
        "chart_type": "band",
        "title": "Temperatures",
        "series_name": "Temperature",
        "label_key": "Parameter",
        "value_key": "Value",
        "data": [
        {"Parameter": "Odrive 1", "Value": 35, "unit": "°C" , "topic" : "Odrive-1-temp"},
        {"Parameter": "Odrive 2", "Value": 45, "unit": "°C", "topic":"Odrive-2-temp"},
        {"Parameter": "Odrive 3", "Value": 45, "unit": "°C", "topic":"Odrive-3-temp"},
        {"Parameter": "Odrive 4", "Value": 45, "unit": "°C", "topic" : "Odrive-4-temp"}
        ]
    },
    "grid": {

        ## Telemetry Client

        ```JSON
        {
            "type": "odrive_http",
            "name": "odrive_telemetry",
            "source": "http://192.168.168.37:8080",
            "base_url": "http://192.168.168.37:8080",
            "topic": "telemetry.odrive",
            "topic_prefix": "odrive",
            "poll_interval_ms": 250,
            "max_data_age_ms": 2000,
            "publish_node_data": true,
            "publish_field_topics": true,
            "enabled": true
        }
        ```

        Le client publie sur l'event bus:
        - `telemetry.odrive` avec le snapshot complet du cycle
        - `odrive.<node_id>` avec le snapshot d'un noeud
        - `odrive.<node_id>.<field>` avec chaque valeur scalaire, par exemple `odrive.31.iq_measured`

        Exemple pour lier un graphe a la telemetrie:

        ```JSON
        {
            "type": "chart",
            "name": "Temperature",
            "data": {
                "chart_type": "band",
                "title": "Temperatures",
                "series_name": "Temperature",
                "label_key": "Parameter",
                "value_key": "Value",
                "data": [
                    {"Parameter": "Odrive 31", "Value": 0, "unit": "°C", "topic": "odrive.31.motor_temp"},
                    {"Parameter": "Odrive 32", "Value": 0, "unit": "°C", "topic": "odrive.32.motor_temp"}
                ]
            }
        }
        ```
    "row": 0,
    "column": 1,
    "row_span": 1,
    "column_span": 1
    }
},

```

##


          "data": {
              #Graphe ampérage avec les 4 odrives en "line"
              # graphe line pour la vélocité des 4 odrives
              #URDF (modèle 3D)
          }
