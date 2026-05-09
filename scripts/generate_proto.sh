#!/usr/bin/env bash
# Run from the project root:
#   bash scripts/generate_proto.sh
#
# Requires: pip install grpcio-tools
set -e
cd "$(dirname "$0")/.."

python -m grpc_tools.protoc \
    -I. \
    --python_out=src/proto_gen \
    proto/RoveTelemetry.proto \
    proto/Battery.proto \
    proto/DriveNodeState.proto \
    proto/imu/Vn300.proto \
    proto/imu/Icm40609.proto \
    proto/core/Position.proto \
    proto/core/Orientation.proto \
    proto/core/Vector3.proto \
    proto/core/JointState.proto

echo "Proto stubs generated in src/proto_gen/"
