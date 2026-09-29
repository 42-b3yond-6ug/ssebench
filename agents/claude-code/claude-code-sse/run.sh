#!/bin/bash
set -euo pipefail

# change cwd to current folder
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

# Ensure HOME is set for model user (uv cache depends on this)
export HOME=/home/model

# Launch the agent (runs as model user via entrypoint)
echo "[run.sh] Launching Claude Code agent..."
# The image holds the environment, and the run container has no internet.
exec uv run --offline --no-sync main.py
