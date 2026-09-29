#!/bin/bash
set -euo pipefail

# log save and preview
DAEMON_LOG_FILE="${SSE_ARCHIVE}/daemon.log"
touch "$DAEMON_LOG_FILE"
tail -f "$DAEMON_LOG_FILE" &

disown

# Log keep-alive mode status
if [ "${SSE_KEEP_ALIVE:-0}" = "1" ]; then
	echo "[ssebench] Keep-alive mode enabled: container will remain running for WebUI"
fi

# Expose the privileged admin socket on the shared archive volume so the
# evaluator (root, in the agent container) can reach it while the agent
# (model) cannot. The daemon binds it 0600.
export SSE_ADMIN_SOCKET="${SSE_ADMIN_SOCKET:-${SSE_ARCHIVE}/admin.sock}"

echo "[ssebench] Starting sdk daemon..."
exec /ssebench/ssebench-daemon 2>&1 | tee "$DAEMON_LOG_FILE"
