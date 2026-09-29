#!/bin/bash
export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"
export CFLAGS="-DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION $CFLAGS"

./autogen.sh
./configure --prefix=$PWD/install --with-zlib --with-lzma --with-schematron
make -j8
make install
