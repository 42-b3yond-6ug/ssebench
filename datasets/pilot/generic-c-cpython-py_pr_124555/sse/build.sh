#!/bin/bash -eu
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"
./configure --without-pymalloc
ASAN_OPTIONS=detect_leaks=0 make -j$(nproc)
test -f python
