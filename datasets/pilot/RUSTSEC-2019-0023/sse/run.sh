#!/bin/bash -eu
cd /ssebench/harness
export RUSTFLAGS="-Zsanitizer=address"
cargo build --offline
./target/debug/RUSTSEC-2019-0023
