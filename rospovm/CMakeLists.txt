cmake_minimum_required(VERSION 3.16)
project(RospOSVM_Qt)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# Compiler warnings and flags
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror=unused-variable -O2 -ltcg)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        add_compile_options(-Weverything -Wno-c++98-compat -Wno-c++98-compat-pedantic)
    endif()
endif()

find_package(Qt6 COMPONENTS Core Gui Widgets REQUIRED)

set(ROSPOSVM_DEFAULT_BINARY_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../rospos/build/rospos.rosp" CACHE FILEPATH
    "Default RospOS binary to preload for the wasm/html frontend")
set(ROSPOSVM_DEFAULT_BLOCKDEV_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../rospos.blockdev" CACHE FILEPATH
    "Default RospOS block device to preload for the wasm/html frontend")

if(EMSCRIPTEN)
    find_package(Qt6 COMPONENTS BundledZLIB REQUIRED)
    set(ROSPOSVM_ZLIB_TARGETS Qt6::ZlibPrivate Qt6::BundledZLIB)
else()
    find_package(ZLIB REQUIRED)
    set(ROSPOSVM_ZLIB_TARGETS ZLIB::ZLIB)
endif()

if(NOT EMSCRIPTEN)
    find_package(KF6SyntaxHighlighting REQUIRED)
endif()

set(ROSPOSVM_HIGHLIGHTING_DIR "${CMAKE_CURRENT_SOURCE_DIR}/highlighting")

# Common backend sources
set(ROSPOSVM_BACKEND_SOURCES
    backend/RospOSVM.cpp
    backend/RospOSVM.h
    backend/InstructionDecoder.cpp
    backend/InstructionDecoder.h
    backend/Register.cpp
    backend/Register.h
    backend/Memory.cpp
    backend/Memory.h
    backend/TTY.cpp
    backend/TTY.h
    backend/Binary.cpp
    backend/Binary.h
    backend/DebugParser.cpp
    backend/DebugParser.h
    backend/Display.cpp
    backend/Display.h
    backend/BlockDevice.cpp
    backend/BlockDevice.h
    backend/BlockDeviceBacking.cpp
    backend/BlockDeviceBacking.h
    backend/Shutdown.cpp
    backend/Shutdown.h
    backend/Logger.cpp
    backend/Logger.h
)

# VM Core Library with state capture (for Qt GUI debugging)
add_library(rosposvm_lib STATIC ${ROSPOSVM_BACKEND_SOURCES})

target_include_directories(rosposvm_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/backend
)
target_link_libraries(rosposvm_lib PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets ${ROSPOSVM_ZLIB_TARGETS})
target_compile_definitions(rosposvm_lib PRIVATE
    ROSPOSVM_ENABLE_STATE_CAPTURE=1
    ROSPOSVM_ENABLE_DEBUG_INFO=1
)

# VM Core Library without state capture (for headless/minimal release builds)
add_library(rosposvm_lib_release STATIC ${ROSPOSVM_BACKEND_SOURCES})

target_include_directories(rosposvm_lib_release PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/backend
)
target_link_libraries(rosposvm_lib_release PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets ${ROSPOSVM_ZLIB_TARGETS})
target_compile_definitions(rosposvm_lib_release PRIVATE
    ROSPOSVM_ENABLE_STATE_CAPTURE=0
    ROSPOSVM_ENABLE_DEBUG_INFO=0
)

if(NOT EMSCRIPTEN)
    # Qt GUI Application
    add_executable(rospovm_qt
        frontend/qt/full/main_qt.cpp
        frontend/qt/full/MainWindow.h
        frontend/qt/full/MainWindow.cpp
        frontend/qt/full/VMController.h
        frontend/qt/full/VMController.cpp
        frontend/qt/full/CodeView.h
        frontend/qt/full/CodeView.cpp
        frontend/qt/full/DebugControlPanel.h
        frontend/qt/full/DebugControlPanel.cpp
        frontend/qt/full/RegisterView.h
        frontend/qt/full/RegisterView.cpp
        frontend/qt/full/MemoryView.h
        frontend/qt/full/MemoryView.cpp
        frontend/qt/full/LogView.h
        frontend/qt/full/LogView.cpp
        frontend/qt/shared/VMControllerCore.h
        frontend/qt/shared/VMControllerCore.cpp
        frontend/qt/shared/TTYWidget.h
        frontend/qt/shared/TTYWidget.cpp
    )

    add_executable(rospovm_minimal
        frontend/qt/minimal/main_minimal_qt.cpp
        frontend/qt/shared/VMControllerCore.h
        frontend/qt/shared/VMControllerCore.cpp
        frontend/qt/shared/TTYWidget.h
        frontend/qt/shared/TTYWidget.cpp
    )

    add_executable(rospovm_headless
        frontend/headless/main_headless.cpp
    )

    target_include_directories(rospovm_qt PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/shared
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/full
        ${CMAKE_CURRENT_SOURCE_DIR}/backend
    )
    target_include_directories(rospovm_minimal PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/shared
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/minimal
        ${CMAKE_CURRENT_SOURCE_DIR}/backend
    )

    target_include_directories(rospovm_headless PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/headless
        ${CMAKE_CURRENT_SOURCE_DIR}/backend
    )

    target_link_libraries(rospovm_qt PRIVATE
        rosposvm_lib
        Qt6::Core
        Qt6::Gui
        Qt6::Widgets
        ${ROSPOSVM_ZLIB_TARGETS}
        KF6::SyntaxHighlighting
    )

    target_link_libraries(rospovm_minimal PRIVATE
        rosposvm_lib_release
        Qt6::Core
        Qt6::Gui
        Qt6::Widgets
        ${ROSPOSVM_ZLIB_TARGETS}
    )

    target_link_libraries(rospovm_headless PRIVATE
        rosposvm_lib_release
        Qt6::Core
    )

    target_compile_definitions(rospovm_qt PRIVATE
        ROSPOSVM_HIGHLIGHTING_DIR="${ROSPOSVM_HIGHLIGHTING_DIR}"
    )

    add_custom_command(TARGET rospovm_qt POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${ROSPOSVM_HIGHLIGHTING_DIR}"
                "$<TARGET_FILE_DIR:rospovm_qt>/highlighting"
    )
endif()

if(EMSCRIPTEN)
    qt_add_executable(rospovm_html
        frontend/html/main_html.cpp
        frontend/qt/shared/VMControllerCore.h
        frontend/qt/shared/VMControllerCore.cpp
        frontend/qt/shared/TTYWidget.h
        frontend/qt/shared/TTYWidget.cpp
    )

    target_include_directories(rospovm_html PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/html
        ${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/shared
        ${CMAKE_CURRENT_SOURCE_DIR}/backend
    )

    target_link_libraries(rospovm_html PRIVATE
        rosposvm_lib_release
        Qt6::Core
        Qt6::Gui
        Qt6::Widgets
        ${ROSPOSVM_ZLIB_TARGETS}
    )

    if(EXISTS "${ROSPOSVM_DEFAULT_BINARY_SOURCE}")
        target_link_options(rospovm_html PRIVATE
            "SHELL:--preload-file ${ROSPOSVM_DEFAULT_BINARY_SOURCE}@rospos.rosp"
        )
    endif()

    if(EXISTS "${ROSPOSVM_DEFAULT_BLOCKDEV_SOURCE}")
        target_link_options(rospovm_html PRIVATE
            "SHELL:--preload-file ${ROSPOSVM_DEFAULT_BLOCKDEV_SOURCE}@rospos.blockdev"
        )
    endif()

    target_compile_definitions(rospovm_html PRIVATE
        ROSPOSVM_WEB_BUILD=1
        ROSPOSVM_DEFAULT_BINARY_FILE="rospos.rosp"
        ROSPOSVM_DEFAULT_BLOCKDEV_FILE="rospos.blockdev"
    )

    set_target_properties(rospovm_html PROPERTIES
        QT_WASM_MEMORY_GROWTH "ON"
        )

endif()
