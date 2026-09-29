#!/usr/bin/env bash
set -euo pipefail

cd /ssebench/harness

unset RUSTFLAGS
cargo clean
cargo build --offline

set +e
DROP2_CNT=$(
  ./target/debug/RUSTSEC-2021-0033 2>&1 \
    | grep -a -o "Dropping 2" \
    | wc -l \
    | tr -d ' '
)
set -e

echo "Dropping 2 count = $DROP2_CNT"

if [[ "$DROP2_CNT" -ge 2 ]]; then
  echo "[FAIL] Vulnerable behavior detected (Dropping 2 twice)"
  exit 1
else
  echo "[PASS] Fixed behavior (Dropping 2 < 2)"
  exit 0
fi

