#!/bin/bash

POC_FILE="$1"

POC_DIR=$(dirname $(realpath "$POC_FILE"))
POC_BASENAME=$(basename "$POC_FILE")

COMPILED_BINARY="$(pwd)/opa"
cp -f "$COMPILED_BINARY" "$POC_DIR/opa"

cd "$POC_DIR"
OUTPUT=$(go run -mod=readonly "$POC_BASENAME" 2>&1)
EXIT_CODE=$?

rm -f "$POC_DIR/opa"
echo "$OUTPUT"

exit $EXIT_CODE