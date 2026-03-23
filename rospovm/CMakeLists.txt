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
    RospOSVM.cpp
    RospOSVM.h
    InstructionDecoder.cpp
    InstructionDecoder.h
    Register.cpp
    Register.h
    Memory.cpp
    Memory.h
    TTY.cpp
    TTY.h
    Binary.cpp
    Binary.h
    DebugParser.cpp
    DebugParser.h
    Display.cpp
    Display.h
    Shutdown.cpp
    Shutdown.h
    Logger.cpp
    Logger.h
)

target_include_directories(rosposvm_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(rosposvm_lib PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets ZLIB::ZLIB KF6::SyntaxHighlighting)
    
# Qt GUI Application
add_executable(rospovm_qt
    main_qt.cpp
    MainWindow.h
    MainWindow.cpp
    VMController.h
    VMController.cpp
    CodeView.h
    CodeView.cpp
    DebugControlPanel.h
    DebugControlPanel.cpp
    RegisterView.h
    RegisterView.cpp
    MemoryView.h
    MemoryView.cpp
    LogView.h
    LogView.cpp
    TTYWidget.h
    TTYWidget.cpp
)

target_link_libraries(rospovm_qt PRIVATE
    rosposvm_lib
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    ZLIB::ZLIB
    KF6::SyntaxHighlighting
)

target_compile_definitions(rospovm_qt PRIVATE
    ROSPOSVM_HIGHLIGHTING_DIR="${ROSPOSVM_HIGHLIGHTING_DIR}"
)

add_custom_command(TARGET rospovm_qt POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${ROSPOSVM_HIGHLIGHTING_DIR}"
            "$<TARGET_FILE_DIR:rospovm_qt>/highlighting"
)
