
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
    }
}
```
