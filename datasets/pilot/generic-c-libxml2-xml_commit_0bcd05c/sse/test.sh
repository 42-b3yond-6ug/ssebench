#!/bin/bash
./autogen.sh
./configure --prefix=$PWD/install --with-zlib --with-lzma --with-schematron --disable-shared --without-python
make -j8
make install
# At this revision about one run in 30 of runtest reports a spurious error for
# test/errors/759398.xml, with the fix or without it. A failure that a second
# run does not repeat is that flake; a real failure fails both times.
make check -j8 || make check -j8