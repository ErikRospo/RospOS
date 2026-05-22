# Requirements for RospOS

"libkf6syntaxhighlighting*"
python
cmake
qt6


rm -rf rospovm/build-wasm && cmake -S rospovm -B rospovm/build-wasm \
  -DCMAKE_TOOLCHAIN_FILE=/home/erospo/Qt/6.10.3/wasm_singlethread/lib/cmake/Qt6/qt.toolchain.cmake \
  -DCMAKE_PREFIX_PATH=/home/erospo/Qt/6.10.3/wasm_singlethread \
  -DQt6_DIR=/home/erospo/Qt/6.10.3/wasm_singlethread/lib/cmake/Qt6 \
  -DCMAKE_EXE_LINKER_FLAGS='-sNO_DISABLE_EXCEPTION_CATCHING' && cmake --build rospovm/build-wasm --target rospovm_html -j16

emsdk 4.0.7 for qt 6.10.3

./configure -qt-host-path ~/Qt/6.10.3/gcc_64 -platform wasm-emscripten -prefix $PWD/qtbase
cmake --build . -t qtbase -t qtdeclarative --parallel
