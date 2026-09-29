#!/bin/bash
set -e

POC_FILE="$1"

# Get absolute path (works with BusyBox)
cd /ssebench
POC_DIR=$(cd "$(dirname "$POC_FILE")" && pwd)
POC_BASENAME=$(basename "$POC_FILE")

cd "$POC_DIR"

go run "$POC_BASENAME"
