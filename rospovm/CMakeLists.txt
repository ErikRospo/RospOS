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
    add_compile_options(-Wall -Wextra -Wpedantic -Werror=unused-variable -O2)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        add_compile_options(-Weverything -Wno-c++98-compat -Wno-c++98-compat-pedantic)
    endif()
endif()

find_package(Qt6 COMPONENTS Core Gui Widgets REQUIRED)
find_package(ZLIB REQUIRED)
find_package(KF6SyntaxHighlighting REQUIRED)

set(ROSPOSVM_HIGHLIGHTING_DIR "${CMAKE_CURRENT_SOURCE_DIR}/highlighting")
# VM Core Library
# Static library containing the VM implementation (no GUI dependencies)
add_library(rosposvm_lib STATIC
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
    backend/Shutdown.cpp
    backend/Shutdown.h
    backend/Logger.cpp
    backend/Logger.h
)

target_include_directories(rosposvm_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/backend
)
target_link_libraries(rosposvm_lib PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets ZLIB::ZLIB KF6::SyntaxHighlighting)
    
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
    ZLIB::ZLIB
    KF6::SyntaxHighlighting
)

target_link_libraries(rospovm_minimal PRIVATE
    rosposvm_lib
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    ZLIB::ZLIB
)

target_link_libraries(rospovm_headless PRIVATE
    rosposvm_lib
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
