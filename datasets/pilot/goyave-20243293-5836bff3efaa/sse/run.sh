#!/bin/bash
set -euo pipefail

POC_FILE="$1"
# The PoC module's go.mod replaces the project with /src/goyave, the agent's working
# tree. Run a copy of the module against the tree this script runs in, the build
# being graded.
PROJECT_DIR=$PWD
POC_DIR=$(mktemp -d)
trap 'rm -rf "$POC_DIR"' EXIT
cp -r "$(dirname "$(realpath "$POC_FILE")")/." "$POC_DIR"
sed -i "s#=> /src/goyave\b#=> $PROJECT_DIR#" "$POC_DIR/go.mod"
cd "$POC_DIR"

go run -mod=readonly "$(basename "$POC_FILE")"
