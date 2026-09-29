#!/bin/bash -eu
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"
./configure --prefix=$(pwd)/vim-build \
    --enable-fail-if-missing \
    --with-features=huge \
    --enable-gui=no \
    --with-tlib=ncurses
make -j32
make install
test -f src/vim