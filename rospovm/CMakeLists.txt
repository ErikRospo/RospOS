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
    add_compile_options(-Wall -Wextra -Wpedantic -Werror=unused-variable -O2 -flto)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        add_compile_options(-Wno-c++98-compat -Wno-c++98-compat-pedantic)
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

find_package(KF6SyntaxHighlighting REQUIRED)

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

function(rosposvm_add_backend target enable_debugging)
    add_library(${target} STATIC ${ROSPOSVM_BACKEND_SOURCES})
    target_include_directories(${target} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/backend")
    target_link_libraries(${target} PUBLIC
        Qt6::Core Qt6::Gui Qt6::Widgets ${ROSPOSVM_ZLIB_TARGETS}
    )
    target_compile_definitions(${target} PRIVATE
        ROSPOSVM_ENABLE_STATE_CAPTURE=${enable_debugging}
        ROSPOSVM_ENABLE_DEBUG_INFO=${enable_debugging}
    )
endfunction()

# Compile separate backend variants so minimal/headless builds omit debugging.
rosposvm_add_backend(rosposvm_lib 1)
rosposvm_add_backend(rosposvm_lib_release 0)

set(ROSPOSVM_QT_SHARED_SOURCES
    frontend/qt/shared/VMControllerCore.h
    frontend/qt/shared/VMControllerCore.cpp
    frontend/qt/shared/TTYWidget.h
    frontend/qt/shared/TTYWidget.cpp
)

set(ROSPOSVM_QT_FULL_SOURCES
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
    frontend/qt/full/BreakpointEvaluator.h
    frontend/qt/full/BreakpointEvaluator.cpp
    frontend/qt/full/MemoryView.h
    frontend/qt/full/MemoryView.cpp
    frontend/qt/full/LogView.h
    frontend/qt/full/LogView.cpp
    frontend/qt/full/BreakpointTextEdit.h
    frontend/qt/full/BreakpointTextEdit.cpp
    lib/exprtk/exprtk.hpp
)

# Desktop and web frontends share the same UI; only their entry points differ.
function(rosposvm_add_gui target variant main_source)
    if(variant STREQUAL "full")
        set(sources ${ROSPOSVM_QT_FULL_SOURCES})
        set(backend rosposvm_lib)
    else()
        set(sources frontend/qt/minimal/MinimalWindow.cpp)
        set(backend rosposvm_lib_release)
    endif()

    if(EMSCRIPTEN)
        qt_add_executable(${target} ${main_source} ${sources} ${ROSPOSVM_QT_SHARED_SOURCES})
        get_filename_component(main_directory "${main_source}" DIRECTORY)
        target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/${main_directory}")
    else()
        add_executable(${target} ${main_source} ${sources} ${ROSPOSVM_QT_SHARED_SOURCES})
    endif()

    target_include_directories(${target} PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/shared"
        "${CMAKE_CURRENT_SOURCE_DIR}/frontend/qt/${variant}"
    )
    # Inherit Qt, zlib and backend headers through PUBLIC usage requirements.
    target_link_libraries(${target} PRIVATE ${backend})

    if(variant STREQUAL "full")
        target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/lib/exprtk")
        target_link_libraries(${target} PRIVATE KF6::SyntaxHighlighting)
        target_compile_definitions(${target} PRIVATE
            ROSPOSVM_HIGHLIGHTING_DIR="${ROSPOSVM_HIGHLIGHTING_DIR}"
        )
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${ROSPOSVM_HIGHLIGHTING_DIR}"
                    "$<TARGET_FILE_DIR:${target}>/highlighting"
            VERBATIM
        )
    endif()
endfunction()

if(EMSCRIPTEN)
    rosposvm_add_gui(rospovm_html full frontend/html/full/main_html.cpp)
    rosposvm_add_gui(rospovm_html_minimal minimal frontend/html/minimal/main_html.cpp)

    target_compile_options(rosposvm_lib_release PRIVATE
        -fexceptions
        -g
    )
    target_compile_options(rospovm_html PRIVATE
        -fexceptions
        -g
    )

    foreach(target IN ITEMS rospovm_html rospovm_html_minimal)
        target_link_options(${target} PRIVATE
            -sNO_DISABLE_EXCEPTION_CATCHING
            -sASSERTIONS=1
            -g
        )
        target_compile_definitions(${target} PRIVATE
            ROSPOSVM_WEB_BUILD=1
            ROSPOSVM_DEFAULT_BINARY_FILE="rospos.rosp"
            ROSPOSVM_DEFAULT_BLOCKDEV_FILE="rospos.blockdev"
            EMSCRIPTEN=1
        )
        set_target_properties(${target} PROPERTIES QT_WASM_MEMORY_GROWTH ON)
    endforeach()

    set(ROSC_SOURCE
        "${CMAKE_CURRENT_SOURCE_DIR}/../rospos/build/rospos_preprocessed.rosc"
    )

    target_link_options(rospovm_html PRIVATE
        "SHELL:--preload-file ${ROSC_SOURCE}@/rospos/build/rospos_preprocessed.rosc"
    )

    # Relink when the source changes, so the embedded copy stays current.
    set_property(TARGET rospovm_html APPEND PROPERTY
        LINK_DEPENDS "${ROSC_SOURCE}"
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
else()
    rosposvm_add_gui(rospovm_qt full frontend/qt/full/main_qt.cpp)
    rosposvm_add_gui(rospovm_minimal minimal frontend/qt/minimal/main_minimal_qt.cpp)

    add_executable(rospovm_headless frontend/headless/main_headless.cpp)
    target_include_directories(rospovm_headless PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/frontend/headless"
    )
    target_link_libraries(rospovm_headless PRIVATE rosposvm_lib_release)

    add_executable(rospovm_fuzz_harness tests/fuzz_harness.cpp)
    target_link_libraries(rospovm_fuzz_harness PRIVATE rosposvm_lib_release)
endif()
