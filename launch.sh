#!/usr/bin/env bash
set -euo pipefail

# All-in-one launcher: build (CMake/make) then run CAPRA_UI.
# Set SKIP_LAUNCH=1 to only run the build step and skip launching the GUI.

cd "$(dirname "$0")"

echo "==> Building CAPRA_UI (build_standalone)..."
mkdir -p build_standalone
pushd build_standalone >/dev/null
# If an existing CMake cache points to a different source dir, remove it
if [ -f CMakeCache.txt ]; then
	cached_source=$(grep -m1 '^CAPRA_UI_SOURCE_DIR:STATIC=' CMakeCache.txt | cut -d'=' -f2- || true)
	actual_source="$(cd .. && pwd)"
	if [ -n "$cached_source" ] && [ "$cached_source" != "$actual_source" ]; then
		echo "Detected stale CMake cache (cached: $cached_source, actual: $actual_source)."
		echo "Removing CMakeCache.txt and CMakeFiles to avoid mismatched configuration."
		rm -rf CMakeCache.txt CMakeFiles pkgRedirects CMakeFiles/* cmake_install.cmake
	fi
fi

# If ROS is available, source it and enable building with ROS2
BUILD_WITH_ROS2_FLAG="-DBUILD_WITH_ROS2=OFF"
if [ -n "${ROS_DISTRO:-}" ] && [ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]; then
	echo "Sourcing /opt/ros/${ROS_DISTRO}/setup.bash"
	# Temporarily disable 'set -u' to avoid unbound variable errors in ROS setup scripts
	set +u
	# shellcheck disable=SC1090
	source "/opt/ros/${ROS_DISTRO}/setup.bash"
	set -u
	BUILD_WITH_ROS2_FLAG="-DBUILD_WITH_ROS2=ON"
elif [ -d "/opt/ros/humble" ] && [ -f "/opt/ros/humble/setup.bash" ]; then
	echo "Sourcing /opt/ros/humble/setup.bash"
	set +u
	# shellcheck disable=SC1090
	source /opt/ros/humble/setup.bash
	set -u
	BUILD_WITH_ROS2_FLAG="-DBUILD_WITH_ROS2=ON"
fi

# Configure and build (use explicit source/build dirs)
cmake -S .. -B . -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_DISABLE_FIND_PACKAGE_GTest=TRUE ${BUILD_WITH_ROS2_FLAG}
make -j$(nproc)
popd >/dev/null

# Force TCP transport for RTSP (UDP support removed)
export OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp"

echo "OPENCV_FFMPEG_CAPTURE_OPTIONS=$OPENCV_FFMPEG_CAPTURE_OPTIONS"

if [ "${SKIP_LAUNCH:-0}" = "1" ]; then
	echo "SKIP_LAUNCH=1 -> build complete, skipping application launch."
	exit 0
fi

echo "==> Launching CAPRA_UI..."
QT_QPA_PLATFORM=xcb ./build_standalone/CAPRA_UI
