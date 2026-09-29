#!/bin/bash
set -euo pipefail

# log save and preview; the results directory is root-only, the archive is the agent's
DAEMON_LOG_FILE="${SSE_RESULTS:-${SSE_ARCHIVE}}/daemon.log"
touch "$DAEMON_LOG_FILE"
tail -f "$DAEMON_LOG_FILE" &

disown

# Log keep-alive mode status
if [ "${SSE_KEEP_ALIVE:-0}" = "1" ]; then
	echo "[ssebench] Keep-alive mode enabled: container will remain running for WebUI"
fi

# /run/ssebench is a volume shared with the agent container. It holds both
# daemon sockets, so it must stay root-owned and read-only to the agent, which
# could otherwise swap a socket for a server of its own. The daemon binds the
# agent socket 0666 and the admin socket 0600 (root only: the evaluator). The
# agent container's entrypoint expects the admin socket at this fixed path.
SOCKET_DIR=/run/ssebench
mkdir -p "$SOCKET_DIR"
chown root:root "$SOCKET_DIR"
chmod 755 "$SOCKET_DIR"
export SSE_DAEMON_SOCKET="${SSE_DAEMON_SOCKET:-${SOCKET_DIR}/sse.sock}"
export SSE_ADMIN_SOCKET="${SOCKET_DIR}/admin.sock"

echo "[ssebench] Starting sdk daemon..."
exec /ssebench/ssebench-daemon 2>&1 | tee "$DAEMON_LOG_FILE"
