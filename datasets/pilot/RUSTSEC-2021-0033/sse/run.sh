#!/usr/bin/env bash
set -euo pipefail

# The harness depends on the project at /src/stack_dst-rs, the agent's working tree. Build
# a copy of it against the tree this script runs in, the build being graded.
PROJECT_DIR=$PWD
HARNESS=$(mktemp -d)
trap 'rm -rf "$HARNESS"' EXIT
cp -r /ssebench/harness/. "$HARNESS"
sed -i "s#\"/src/stack_dst-rs\"#\"$PROJECT_DIR\"#" "$HARNESS/Cargo.toml"
cd "$HARNESS"

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

