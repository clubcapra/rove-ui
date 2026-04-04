
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
        {"Parameter": "Odrive 1", "Value": 35, "unit": "°C"},
        {"Parameter": "Odrive 2", "Value": 45, "unit": "°C"},
        {"Parameter": "Odrive 3", "Value": 45, "unit": "°C"},
        {"Parameter": "Odrive 4", "Value": 45, "unit": "°C"}
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