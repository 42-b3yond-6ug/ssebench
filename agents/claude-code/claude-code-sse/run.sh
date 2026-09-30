#!/bin/bash
set -euo pipefail

# change cwd to current folder
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR" || exit 1

# The run container reaches the LiteLLM proxy only: turn off Claude Code's
# update checks, telemetry, error reports and plugin marketplace installs.
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL=1

# Launch the agent (runs as model user via entrypoint)
echo "[run.sh] Launching Claude Code agent..."
# The image holds the environment, and the run container has no internet.
exec uv run --offline --no-sync main.py
