#!/bin/bash

CRASH_KEYWORDS=(
  "AddressSanitizer"
  "Segmentation fault"
  "(core dumped)"
)
logfile=$(mktemp)

export ASAN_OPTIONS=detect_leaks=0
./build/jq_fuzz_fixed $1 \
  > >(tee -a "$logfile") \
  2> >(tee -a "$logfile" >&2)

for kw in "${CRASH_KEYWORDS[@]}"; do
  if grep -q "$kw" "$logfile"; then
    exit 1
  fi
done

exit 0
