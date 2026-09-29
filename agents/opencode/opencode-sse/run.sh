#!/bin/bash
set -euo pipefail

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

export HOME=/home/model

echo "[run.sh] Launching OpenCode agent..."
exec uv run --frozen --no-dev main.py
