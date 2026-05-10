#!/usr/bin/env bash
set +u
source /opt/ros/humble/setup.bash

ros2 topic pub --once /dynamic_joint_states control_msgs/msg/DynamicJointState "{
  header: {stamp: {sec: 0, nanosec: 0}, frame_id: 'base_link'},
  joint_names: ['track_fl_j', 'track_rl_j', 'track_fr_j', 'track_rr_j'],
  interface_values: [
    {interface_names: ['velocity', 'motor_temperature', 'fet_temperature'], values: [2, 52.3, 34.1]},
    {interface_names: ['velocity', 'motor_temperature', 'fet_temperature'], values: [3, 32.0, 36.5]},
    {interface_names: ['velocity', 'motor_temperature', 'fet_temperature'], values: [-2, 35.8, 33.9]},
    {interface_names: ['velocity', 'motor_temperature', 'fet_temperature'], values: [-3, 54.5, 44.7]}
  ]
}"
