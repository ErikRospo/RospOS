cmake_minimum_required(VERSION 3.16)
project(RospOSVM_Qt)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 COMPONENTS Core Gui Widgets REQUIRED)

# VM Core Library
add_library(rosposvm_lib STATIC
    RospOSVM.cpp
    InstructionDecoder.cpp
    Register.cpp
    Memory.cpp
    TTY.cpp
    Binary.cpp
    Display.cpp
    Shutdown.cpp
    Logger.cpp
)

target_include_directories(rosposvm_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(rosposvm_lib PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets)

# Qt GUI Application
add_executable(rospovm_qt
    main_qt.cpp
    MainWindow.h
    MainWindow.cpp
    VMController.h
    VMController.cpp
    DisassemblyView.h
    DisassemblyView.cpp
    RegisterView.h
    RegisterView.cpp
    MemoryView.h
    MemoryView.cpp
    LogView.h
    LogView.cpp
)

target_link_libraries(rospovm_qt PRIVATE
    rosposvm_lib
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
)
