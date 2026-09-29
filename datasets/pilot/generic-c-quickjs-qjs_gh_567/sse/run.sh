#!/bin/bash

CRASH_KEYWORDS=(
  "AddressSanitizer"
  "Segmentation fault"
  "(core dumped)"
)
logfile=$(mktemp)

export ASAN_OPTIONS=detect_leaks=1
cat <<EOF > a.js
import * as a from "./b.js"
export function f(x) { return a.g(x) }
EOF
cat <<EOF > b.js
import {f} from "./a.js"
export {f}
export function g(x) { return x }
EOF
build/qjs b.js \
  > >(tee -a "$logfile") \
  2> >(tee -a "$logfile" >&2)

for kw in "${CRASH_KEYWORDS[@]}"; do
  if grep -q "$kw" "$logfile"; then
    exit 1
  fi
done

exit 0
