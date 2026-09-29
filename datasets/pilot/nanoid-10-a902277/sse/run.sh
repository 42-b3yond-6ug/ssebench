#!/bin/bash -eu
cd /ssebench/harness

unset RUSTFLAGS

cargo clean
cargo build

DEBUG_DIR="./target/debug"

if [[ ! -d "$DEBUG_DIR" ]]; then
  echo "ERROR: $DEBUG_DIR not found" >&2
  exit 2
fi

BIN="$(
  find "$DEBUG_DIR" -maxdepth 1 -type f -executable \
    ! -name '*.d' ! -name '*.rlib' \
    -printf '%T@ %p\n' \
  | sort -nr \
  | awk 'NR==1{print $2}' || true
)"

if [[ -z "$BIN" || ! -x "$BIN" ]]; then
  echo "ERROR: Could not locate PoC executable in $DEBUG_DIR" >&2
  exit 2
fi

echo "Using PoC binary: $BIN"

OUT="$("$BIN" 2>&1 || true)"
echo "$OUT"

b58="$(echo "$OUT" | awk -F= '/base58_symbols=/{print $2}' | tail -n1)"
b62="$(echo "$OUT" | awk -F= '/base62_symbols=/{print $2}' | tail -n1)"

if [[ -z "${b58:-}" ]]; then
  b58="$(echo "$OUT" | awk '/symbols generated from nano_id::base58/{print $1}' | tail -n1)"
fi
if [[ -z "${b62:-}" ]]; then
  b62="$(echo "$OUT" | awk '/symbols generated from nano_id::base62/{print $1}' | tail -n1)"
fi

if ! [[ "${b58:-}" =~ ^[0-9]+$ && "${b62:-}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: Could not parse symbol counts from PoC output" >&2
  exit 2
fi

if (( b58 >= 58 && b62 >= 62 )); then
  echo "OK: vulnerability fixed (base58=$b58, base62=$b62)"
  exit 0
else
  echo "FAIL: vulnerability NOT fixed (base58=$b58, base62=$b62)" >&2
  exit 1
fi

