#!/bin/bash -eu
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$(pwd)/exiv2-build
make -j$(nproc)
make install
test -f ./bin/exiv2
