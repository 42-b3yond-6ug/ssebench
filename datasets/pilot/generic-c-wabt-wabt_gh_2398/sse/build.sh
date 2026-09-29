#!/bin/bash -eu
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"
mkdir -p build
cd build
cmake ..
make -j32 wasm-interp
test -f wasm-interp
