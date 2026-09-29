#!/bin/bash -eu
cd /ssebench/harness
export RUSTFLAGS="-Zsanitizer=address"
RUSTFLAGS="-A deprecated -A warnings" cargo build --offline
./target/debug/RUSTSEC-2019-0034
