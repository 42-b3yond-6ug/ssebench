#!/bin/bash
set -euo pipefail

# change cwd to current folder
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

# The entrypoint keeps root's environment; Codex keeps its configuration in HOME.
export HOME=/home/model

# Launch the agent
echo "[run.sh] Launching Codex agent..."
uv run --frozen --no-dev main.py
