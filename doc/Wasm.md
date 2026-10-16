# WebAssembly builds

Build both HTML frontends with `make frontend_wasm`, or select
`frontend_wasm_full` / `frontend_wasm_minimal` individually. The output packages
are in `rospovm/build-wasm/full_dist` and `rospovm/build-wasm/minimal_dist`.

The Make targets download the pinned Qt version into `.deps/qt/` and use those
kits for both native and WebAssembly builds. The default is Qt `6.12.0`; change
it with `QT_VERSION=...`. `make qt_sdk` downloads the native host kit and the
single-threaded WebAssembly kit explicitly. The download uses the community
`aqtinstall` client and Qt's published binary packages; no Qt Maintenance Tool
installation is needed. Python 3 and network access are needed on the first
build. Downloaded kits and the installer environment stay under ignored
`.deps/`.

Web builds default to `WASM_BUILD_TYPE=MinSizeRel`. This configuration uses
`-Oz` during compilation and linking, LTO, no C++ debug information, and no
Emscripten runtime assertions. Unused image format plugins are excluded;
built-in PNG support and the SVG image and icon plugins remain available.
C++ exceptions, filesystem support, and the full frontend's RospOS debugger
features are retained. Native build flags are unchanged.

Choose another configuration when needed:

```sh
make frontend_wasm WASM_BUILD_TYPE=Debug
make frontend_wasm WASM_BUILD_TYPE=RelWithDebInfo
make frontend_wasm WASM_BUILD_TYPE=Release
```

`Debug` uses `-O0`, C++ debug information, and runtime assertions.
`RelWithDebInfo` uses `-O2` with debug information and assertions. `Release`
uses `-O3` without debug information or assertions; compare it with
`MinSizeRel` when VM execution speed matters more than download size.
Changing the configuration rebuilds the application and backend objects in
the same build directory. The syntax highlighting dependency retains its
separate Release configuration.

For direct CMake builds, select the configuration with
`-DCMAKE_BUILD_TYPE=MinSizeRel` (or another configuration above). An empty
build type defaults to `MinSizeRel` only for WebAssembly.

For direct CMake builds, first run `make qt_sdk`, then set `Qt6_DIR` to the
downloaded Wasm kit and `QT_HOST_PATH` to its matching native kit. Qt 6.12 also
needs `Qt6HostInfo_DIR` to point at the Wasm kit's
`lib/cmake/Qt6HostInfo` directory. The Make targets set these paths
automatically. You can change the download root with `QT_ROOT` and override
`QT_NATIVE` or `QT_WASM` when using an existing installation.

Override `QT_WASM_HOST_INFO_DIR` if your installation puts that package in a
different directory.

Deployment packages contain the original `.wasm`, `.js`, and `.data` files;
the build does not generate compressed copies.
