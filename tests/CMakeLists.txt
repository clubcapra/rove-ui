cmake_minimum_required(VERSION 3.16)

# Configuration des tests
enable_testing()

# Trouver Google Test
find_package(GTest REQUIRED)
include_directories(${GTEST_INCLUDE_DIRS})

# Trouver Qt6
find_package(Qt6 REQUIRED COMPONENTS Core Widgets WebEngineWidgets Test)

# Trouver OpenCV
find_package(OpenCV REQUIRED)

# Tests unitaires pour ConfigManager
add_executable(test_config_manager
    unit/test_config_manager.cpp
    ../src/core/config_manager.cpp
)

target_link_libraries(test_config_manager
    ${GTEST_LIBRARIES}
    pthread
    Qt6::Core
    Qt6::Widgets
)

target_include_directories(test_config_manager PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_test(NAME ConfigManagerTest COMMAND test_config_manager)

# Tests unitaires pour RtspViewer
add_executable(test_rtsp_viewer
    unit/test_rtsp_viewer.cpp
    ../src/views/rtsp_viewer.cpp
)

target_link_libraries(test_rtsp_viewer
    ${GTEST_LIBRARIES}
    pthread
    Qt6::Core
    Qt6::Widgets
    Qt6::Test
    ${OpenCV_LIBS}
)

target_include_directories(test_rtsp_viewer PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${OpenCV_INCLUDE_DIRS}
)

add_test(NAME RtspViewerTest COMMAND test_rtsp_viewer)

# Tests unitaires pour MapViewer
add_executable(test_map_viewer
    unit/test_map_viewer.cpp
    ../src/views/map_viewer.cpp
)

target_link_libraries(test_map_viewer
    ${GTEST_LIBRARIES}
    pthread
    Qt6::Core
    Qt6::Widgets
    Qt6::WebEngineWidgets
    Qt6::Test
)

target_include_directories(test_map_viewer PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_test(NAME MapViewerTest COMMAND test_map_viewer)

# Ajouter une cible pour exécuter tous les tests
add_custom_target(run_tests
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    DEPENDS test_config_manager test_rtsp_viewer test_map_viewer
)
