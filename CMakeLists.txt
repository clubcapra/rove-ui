cmake_minimum_required(VERSION 3.5)

project(CAPRA_UI VERSION 0.1 LANGUAGES C CXX)

set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Option to build without ROS 2
option(BUILD_WITH_ROS2 "Build with ROS 2 support" ON)
option(BUILD_PCL_VIS "Enable PCL/VTK visualization features" OFF)

# Find Qt packages - Use Qt6
find_package(Qt6 REQUIRED COMPONENTS Widgets WebEngineWidgets OpenGLWidgets)
set(QT_VERSION_MAJOR 6)
message(STATUS "Using Qt6")

# Find OpenCV for RTSP streaming
find_package(OpenCV REQUIRED)

# Source files organized by directory
set(PROJECT_SOURCES
        src/main.cpp
        src/ui/capra_ui.cpp
        src/ui/capra_ui.h
        src/ui/capra_ui.ui
        src/ui/config_dialog.cpp
        src/ui/config_dialog.h
        src/views/map_viewer.cpp
        src/views/map_viewer.h
        src/views/pointcloud_viewer.cpp
        src/views/pointcloud_viewer.h
        src/views/layout_panel.cpp
        src/views/layout_panel.h
        src/views/web_page.cpp
        src/views/web_page.h
        src/core/config_manager.cpp
        src/core/config_manager.h
)

# Conditionally add ROS 2 and PCL files
if(BUILD_WITH_ROS2)
    message(STATUS "Building with ROS 2 support")
    
    # Find ROS 2 packages
    find_package(rclcpp REQUIRED)
    find_package(sensor_msgs REQUIRED)
    find_package(geometry_msgs REQUIRED)
    # pcl_conversions and full PCL/VTK export transitive GUI deps; only find when visualization enabled
    if(BUILD_PCL_VIS)
        find_package(pcl_conversions REQUIRED)
    endif()
    
    # PCL/VTK visualization is optional because some system PCL/VTK export Qt5 targets
    if(BUILD_PCL_VIS)
        message(STATUS "Building with PCL/VTK visualization support")
        find_package(PCL REQUIRED COMPONENTS common io visualization)
        add_compile_definitions(WITH_PCL_VIS)
    else()
        message(STATUS "PCL/VTK visualization disabled (BUILD_PCL_VIS=OFF)")
        # Do not find PCL visualization components to avoid pulling VTK/Qt5
    endif()
    
    list(APPEND PROJECT_SOURCES
        src/adapters/ros_node.cpp
        src/adapters/ros_node.h
    )
    
    add_compile_definitions(WITH_ROS2)
else()
    message(STATUS "Building WITHOUT ROS 2 support (standalone mode)")
endif()

qt_add_executable(CAPRA_UI
    MANUAL_FINALIZATION
    ${PROJECT_SOURCES}
)

target_link_libraries(CAPRA_UI PRIVATE
    Qt${QT_VERSION_MAJOR}::Widgets
    Qt${QT_VERSION_MAJOR}::WebEngineWidgets
    Qt${QT_VERSION_MAJOR}::OpenGLWidgets
    ${OpenCV_LIBS}
)

if(BUILD_WITH_ROS2)
    if(BUILD_PCL_VIS)
        target_link_libraries(CAPRA_UI PRIVATE
            ${PCL_LIBRARIES}
        )
    endif()

    # Link ROS 2 libraries
    # Debug: print package INTERFACES/LIBRARIES to detect Qt5 references
    if(BUILD_PCL_VIS)
        foreach(_pkg rclcpp sensor_msgs geometry_msgs pcl_conversions)
            message(STATUS "DEBUG: ${_pkg}_INTERFACES=${${_pkg}_INTERFACES}")
            message(STATUS "DEBUG: ${_pkg}_LIBRARIES=${${_pkg}_LIBRARIES}")
        endforeach()
    else()
        foreach(_pkg rclcpp sensor_msgs geometry_msgs)
            message(STATUS "DEBUG: ${_pkg}_INTERFACES=${${_pkg}_INTERFACES}")
            message(STATUS "DEBUG: ${_pkg}_LIBRARIES=${${_pkg}_LIBRARIES}")
        endforeach()
    endif()
    ament_target_dependencies(CAPRA_UI PUBLIC
        rclcpp
        sensor_msgs
        geometry_msgs
    )
    if(BUILD_PCL_VIS)
        ament_target_dependencies(CAPRA_UI PUBLIC pcl_conversions)
    endif()
    
    if(BUILD_PCL_VIS)
        target_include_directories(CAPRA_UI PRIVATE
            ${PCL_INCLUDE_DIRS}
            ${OpenCV_INCLUDE_DIRS}
        )
        
        target_compile_definitions(CAPRA_UI PRIVATE
            ${PCL_DEFINITIONS}
        )
    else()
        # Ensure OpenCV include dirs are available even without PCL visualization
        target_include_directories(CAPRA_UI PRIVATE
            ${OpenCV_INCLUDE_DIRS}
        )
    endif()
endif()

target_include_directories(CAPRA_UI PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${OpenCV_INCLUDE_DIRS}
)

# Add tests subdirectory (optionnel - nécessite Google Test)
if(EXISTS "${CMAKE_SOURCE_DIR}/tests/CMakeLists.txt")
    find_package(GTest QUIET)
    if(GTest_FOUND AND EXISTS "${CMAKE_SOURCE_DIR}/tests/unit/test_config_manager.cpp" AND EXISTS "${CMAKE_SOURCE_DIR}/tests/unit/test_rtsp_viewer.cpp" AND EXISTS "${CMAKE_SOURCE_DIR}/tests/unit/test_map_viewer.cpp")
        enable_testing()
        add_subdirectory(tests)
        message(STATUS "Tests enabled (GTest found and test sources exist)")
    else()
        message(STATUS "Tests disabled (GTest not found or required unit test sources missing)")
    endif()
endif()

# Qt for iOS sets MACOSX_BUNDLE_GUI_IDENTIFIER automatically since Qt 6.1.
set(BUNDLE_ID_OPTION MACOSX_BUNDLE_GUI_IDENTIFIER com.example.CAPRA_UI)
set_target_properties(CAPRA_UI PROPERTIES
    ${BUNDLE_ID_OPTION}
    MACOSX_BUNDLE_BUNDLE_VERSION ${PROJECT_VERSION}
    MACOSX_BUNDLE_SHORT_VERSION_STRING ${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}
    MACOSX_BUNDLE TRUE
    WIN32_EXECUTABLE TRUE
)

include(GNUInstallDirs)
install(TARGETS CAPRA_UI
    BUNDLE DESTINATION .
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

if(QT_VERSION_MAJOR EQUAL 6)
    qt_finalize_executable(CAPRA_UI)
endif()
