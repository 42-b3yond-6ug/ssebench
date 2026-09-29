#!/bin/bash

POC_FILE="$1"

POC_DIR=$(dirname $(realpath "$POC_FILE"))
POC_BASENAME=$(basename "$POC_FILE")

cd "$POC_DIR"

OUTPUT=$(go run -mod=mod "$POC_BASENAME" 2>&1)
EXIT_CODE=$?

echo "$OUTPUT"

exit $EXIT_CODE