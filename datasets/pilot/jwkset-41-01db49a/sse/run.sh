#!/bin/bash

POC_FILE="$1"

POC_DIR=$(dirname $(realpath "$POC_FILE"))
POC_BASENAME=$(basename "$POC_FILE")

cd "$POC_DIR"

OUTPUT=$(go run -mod=readonly "$POC_BASENAME" 2>&1)
EXIT_CODE=$?

echo "$OUTPUT"
echo "Exit code: $EXIT_CODE"

OLD_KID=$(echo "$OUTPUT" | grep -m1 "Old key. kid=" | sed -n 's/.*kid=\([a-f0-9\-]*\).*/\1/p')
NEW_KID=$(echo "$OUTPUT" | grep -m1 "New key. kid=" | sed -n 's/.*kid=\([a-f0-9\-]*\).*/\1/p')

if [ "$OLD_KID" = "$NEW_KID" ]; then
    exit 1
else
    exit 0
fi
