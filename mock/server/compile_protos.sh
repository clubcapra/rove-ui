#!/usr/bin/env bash
# Run from project root:  bash mock/server/compile_protos.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$REPO_ROOT/mock/server/proto_gen"
mkdir -p "$OUT/proto/core" "$OUT/proto/imu"

protoc \
  -I "$REPO_ROOT" \
  --python_out="$OUT" \
  proto/Battery.proto \
  proto/DriveNodeState.proto \
  proto/RoveTelemetry.proto \
  proto/RoveControl.proto \
  proto/core/JointState.proto \
  proto/core/Vector3.proto \
  proto/core/Position.proto \
  proto/core/Orientation.proto \
  proto/imu/Vn300.proto \
  proto/imu/Icm40609.proto

# Ensure Python packages
touch "$OUT/__init__.py" \
      "$OUT/proto/__init__.py" \
      "$OUT/proto/core/__init__.py" \
      "$OUT/proto/imu/__init__.py"

echo "Proto files generated in $OUT"
