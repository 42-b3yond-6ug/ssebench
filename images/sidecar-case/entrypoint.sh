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

echo "[ssebench] Starting sdk daemon..."
exec /ssebench/ssebench-daemon 2>&1 | tee "$DAEMON_LOG_FILE"
