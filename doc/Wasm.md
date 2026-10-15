# WebAssembly builds

Build both HTML frontends with `make frontend_wasm`, or select
`frontend_wasm_full` / `frontend_wasm_minimal` individually. The output packages
are in `rospovm/build-wasm/full_dist` and `rospovm/build-wasm/minimal_dist`.

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

Deployment packages contain the original `.wasm`, `.js`, and `.data` files;
the build does not generate compressed copies.
