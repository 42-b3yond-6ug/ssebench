#!/bin/bash
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"
./autogen.sh
./configure --prefix=$PWD/install
make -j$(nproc)
make install
