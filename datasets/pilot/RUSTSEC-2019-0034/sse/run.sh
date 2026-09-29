#!/bin/bash -eu
# The harness depends on the project at /src/http, the agent's working tree. Build
# a copy of it against the tree this script runs in, the build being graded.
PROJECT_DIR=$PWD
HARNESS=$(mktemp -d)
trap 'rm -rf "$HARNESS"' EXIT
cp -r /ssebench/harness/. "$HARNESS"
sed -i "s#\"/src/http\"#\"$PROJECT_DIR\"#" "$HARNESS/Cargo.toml"
cd "$HARNESS"
export RUSTFLAGS="-Zsanitizer=address"
RUSTFLAGS="-A deprecated -A warnings" cargo build --offline
./target/debug/RUSTSEC-2019-0034
