#!/bin/bash -eu
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"

mkdir -p build
cd build
cmake .. \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DLEMON_EXECUTABLE=/usr/bin/lemon \
    -DENABLE_ASAN=1 \
    -DENABLE_WERROR=OFF

ninja -j16