#!/bin/bash

POC_FILE="$1"

# The PoC module's go.mod replaces the project with /src/jwkset, the agent's working
# tree. Run a copy of the module against the tree this script runs in, the build
# being graded.
PROJECT_DIR=$PWD
POC_DIR=$(mktemp -d)
trap 'rm -rf "$POC_DIR"' EXIT
cp -r "$(dirname "$(realpath "$POC_FILE")")/." "$POC_DIR"
sed -i "s#=> /src/jwkset\b#=> $PROJECT_DIR#" "$POC_DIR/go.mod"
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
