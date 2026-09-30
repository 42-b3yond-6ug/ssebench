#!/bin/bash
set -euo pipefail

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

echo "[run.sh] Launching OpenCode agent..."
# The image holds the environment, and the run container has no internet.
exec uv run --offline --no-sync main.py
