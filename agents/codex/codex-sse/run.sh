#!/bin/bash
set -euo pipefail

# change cwd to current folder
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

# Launch the agent
echo "[run.sh] Launching Codex agent..."
# The image holds the environment, and the run container has no internet.
exec uv run --offline --no-sync main.py
