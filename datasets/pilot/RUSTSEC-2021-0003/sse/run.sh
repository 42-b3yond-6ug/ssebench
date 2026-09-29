#!/bin/bash -eu
cd /ssebench/harness
#export RUSTFLAGS="-Zsanitizer=address"
unset RUSTFLAGS
cargo clean
cargo build
./target/debug/RUSTSEC-2021-0003
