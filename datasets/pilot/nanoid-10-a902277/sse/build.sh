#!/bin/bash -eu
# The harness depends on the project at /src/nano-id, the agent's working tree. Build
# a copy of it against the tree this script runs in, the build being graded.
PROJECT_DIR=$PWD
HARNESS=$(mktemp -d)
trap 'rm -rf "$HARNESS"' EXIT
cp -r /ssebench/harness/. "$HARNESS"
sed -i "s#\"/src/nano-id\"#\"$PROJECT_DIR\"#" "$HARNESS/Cargo.toml"
cd "$HARNESS"
cargo build
