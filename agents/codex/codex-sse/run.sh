#!/bin/bash
set -euo pipefail

# change cwd to current folder
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

# Launch the agent
echo "[run.sh] Launching Codex agent..."
uv run --frozen --no-dev main.py