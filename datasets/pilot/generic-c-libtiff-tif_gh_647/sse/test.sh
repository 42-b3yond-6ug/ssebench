#!/bin/bash
./autogen.sh
./configure --prefix=$PWD/install
make -j8
make install
# Serially: tiffcp-32bpp-None-jpeg.sh and tiffcrop-32bpp-None-jpeg.sh read the
# image that tiff2rgba-32bpp-None-jpeg.sh writes, and the test suite does not
# order them, so a parallel run fails at random.
make check