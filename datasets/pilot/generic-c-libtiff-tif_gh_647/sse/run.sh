#!/bin/bash

export CC="clang"
export CXX="clang++"
export CFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export CXXFLAGS="-g -O0 -Wno-everything -fsanitize=address"
export LDFLAGS="-fsanitize=address"

cat<<EOF > poc.c
#include <tiffio.h>

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include <stdint.h>

int main(int argc, char** argv) {
	if (argc < 2) {
		printf("Usage: %s <file>\n", argv[0]);
		return 1;
	}

	TIFF* tif = TIFFOpen(argv[1], "rh");
	if (tif == 0) return 1;
	TIFFReadGPSDirectory(tif, 4);
	TIFFClose(tif);
	return 0;
}
EOF

if [ -z "$CC" ]; then
    clang  -I./install/include -L./install/lib -Wl,-rpath=$PWD/install/lib -ltiff -lz -ljpeg -llzma -o poc-647 poc.c
else
    $CC $CFLAGS -I./install/include -L./install/lib -Wl,-rpath=$PWD/install/lib -ltiff -lz -ljpeg -llzma -o poc-647 poc.c
fi

test -f poc-647

CRASH_KEYWORDS=(
  "AddressSanitizer"
  "Segmentation fault"
  "(core dumped)"
)
logfile=$(mktemp)

export ASAN_OPTIONS=detect_leaks=0
./poc-647 $1 \
  > >(tee -a "$logfile") \
  2> >(tee -a "$logfile" >&2)

for kw in "${CRASH_KEYWORDS[@]}"; do
  if grep -q "$kw" "$logfile"; then
    exit 1
  fi
done

exit 0
