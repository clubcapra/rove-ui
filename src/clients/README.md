http://192.168.168.37:8080/docs




GET ` get/odrive_31/data`
```JSON
{
  "active_errors": 1,
  "axis_error": 1,
  "axis_state": 1,
  "bus_current": 1,
  "bus_voltage": 1,
  "count_cpr": 1,
  "disarm_reason": 1,
  "electrical_power": 1,
  "fet_temp": 1,
  "iq_measured": 1,
  "iq_setpoint": 1,
  "mechanical_power": 1,
  "motor_temp": 1,
  "node_id": 1,
  "pos_estimate": 1,
  "procedure_result": 1,
  "shadow_count": 1,
  "timestamp_ns": 1,
  "torque_estimate": 1,
  "torque_target": 1,
  "trajectory_done": true,
  "vel_estimate": 1
}

```


`get/odrive_31/info`


``` JSON
{
  "command_mode": {
    "type": "Rest"
  },
  "command_port": 0,
  "command_schema": [
    {
      "description": "string",
      "name": "string",
      "type_name": "string",
      "unit": null
    }
  ],
  "data_port": 0,
  "data_schema": [
    {
      "description": "string",
      "name": "string",
      "type_name": "string",
      "unit": null
    }
  ],
  "display_name": "string",
  "id": "string",
  "udp_protocol": {
    "command_protocol": {
      "description": "string",
      "flow": "string",
      "packets": [
        {
          "description": "string",
          "header_hex": "string",
          "name": "string",
          "payload_example": null
        }
      ]
    },
    "data_subscription": {
      "data_push_packet": {
        "description": "string",
        "header_hex": "string",
        "name": "string",
        "payload_example": null
      },
      "description": "string",
      "flow": "string",
      "subscribe_packet": {
        "description": "string",
        "header_hex": "string",
        "name": "string",
        "payload_example": null
      },
      "unsubscribe_packet": {
        "description": "string",
        "header_hex": "string",
        "name": "string",
        "payload_example": null
      }
    },
    "header_format": "string"
  }
}

```

`GET/discover`

``` JSON
{
  "sensors": [
    {
      "id": "odrive_33",
      "display_name": "ODrive Node 33",
      "command_mode": {
        "type": "Stream",
        "interval_ms": 250
      },
      "data_port": 5004,
      "command_port": 5005,
      "endpoints": {
        "info": "/odrive_33/info",
        "data": "/odrive_33/data",
        "command": "/odrive_33/command",
        "estop": "/odrive_33/estop",
        "config": "/odrive_33/config",
        "calibrate": "/odrive_33/calibrate",
        "endpoints": "/odrive_33/endpoints"
      }
    },
    {
      "id": "odrive_32",
      "display_name": "ODrive Node 32",
      "command_mode": {
        "type": "Stream",
        "interval_ms": 250
      },
      "data_port": 5006,
      "command_port": 5007,
      "endpoints": {
        "info": "/odrive_32/info",
        "data": "/odrive_32/data",
        "command": "/odrive_32/command",
        "estop": "/odrive_32/estop",
        "config": "/odrive_32/config",
        "calibrate": "/odrive_32/calibrate",
        "endpoints": "/odrive_32/endpoints"
      }
    },
    {
      "id": "odrive_34",
      "display_name": "ODrive Node 34",
      "command_mode": {
        "type": "Stream",
        "interval_ms": 250
      },
      "data_port": 5002,
      "command_port": 5003,
      "endpoints": {
        "info": "/odrive_34/info",
        "data": "/odrive_34/data",
        "command": "/odrive_34/command",
        "estop": "/odrive_34/estop",
        "config": "/odrive_34/config",
        "calibrate": "/odrive_34/calibrate",
        "endpoints": "/odrive_34/endpoints"
      }
    },
    {
      "id": "odrive_31",
      "display_name": "ODrive Node 31",
      "command_mode": {
        "type": "Stream",
        "interval_ms": 250
      },
      "data_port": 5000,
      "command_port": 5001,
      "endpoints": {
        "info": "/odrive_31/info",
        "data": "/odrive_31/data",
        "command": "/odrive_31/command",
        "estop": "/odrive_31/estop",
        "config": "/odrive_31/config",
        "calibrate": "/odrive_31/calibrate",
        "endpoints": "/odrive_31/endpoints"
      }
    }
  ]
}


```