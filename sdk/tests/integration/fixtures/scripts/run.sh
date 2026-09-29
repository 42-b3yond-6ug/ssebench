#!/bin/bash
# The PoC module (go.mod next to poc.go, prepared in the image) replaces the
# project with /src/buggy, as the pilot's Go tasks do.
set -e

POC_FILE="$1"
cd "$(dirname "$POC_FILE")"
go run "$(basename "$POC_FILE")"
