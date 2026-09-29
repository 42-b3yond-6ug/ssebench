#!/bin/bash
set -euo pipefail

POC_FILE="$1"
POC_DIR="$(dirname "$(realpath "$POC_FILE")")"
cd "$POC_DIR"

go run -mod=readonly "$POC_FILE"
