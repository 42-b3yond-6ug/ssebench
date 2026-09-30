#!/bin/bash
# Fake agent: runs as the unprivileged `model` user inside a real agent
# container (the sandbox, or the agent container of a sidecar run) and tries
# every known way to reach information the benchmark must withhold. It exits
# non-zero if any bypass succeeds or any allowed action is wrongly blocked.
#
# Usage: fake_agent.sh <difficulty> <source_dir>
#
# The daemon's endpoints default to the sandbox layout; a sidecar run sets
# SSE_DAEMON_SOCKET, SSE_ADMIN_SOCKET and SSE_DAEMON_HTTP.
#
# Difficulty -> allowed bencher actions (mirrors the daemon gate):
#   build         allowed when difficulty <= 3
#   function_test allowed when difficulty <= 2
#   run_poc       allowed when difficulty <= 1
#   intent_test   allowed when difficulty <= 0

set -u

DIFFICULTY="${1:?usage: fake_agent.sh <difficulty> <source_dir>}"
SOURCE_DIR="${2:?usage: fake_agent.sh <difficulty> <source_dir>}"

SOCK="${SSE_DAEMON_SOCKET:-/tmp/sse.sock}"
ADMIN_SOCK="${SSE_ADMIN_SOCKET:-/run/ssebench/admin.sock}"
HTTP="${SSE_DAEMON_HTTP:-http://localhost:4263}"

fail=0
ok()   { echo "  ok   - $1"; }
bad()  { echo "  FAIL - $1"; fail=1; }

# Status of a POST to a bencher action over the agent-facing unix socket.
bencher_unix() {
	curl -s -o /dev/null -w '%{http_code}' --unix-socket "$SOCK" \
		-X POST "http://d/tool/bencher?action=$1" \
		-H 'Content-Type: application/json' -d '{}'
}
# Same over the HTTP listener.
bencher_http() {
	curl -s -o /dev/null -w '%{http_code}' \
		-X POST "$HTTP/tool/bencher?action=$1" \
		-H 'Content-Type: application/json' -d '{}'
}

action_allowed() {
	case "$1" in
	build) [ "$DIFFICULTY" -le 3 ] ;;
	function_test) [ "$DIFFICULTY" -le 2 ] ;;
	run_poc) [ "$DIFFICULTY" -le 1 ] ;;
	intent_test) [ "$DIFFICULTY" -le 0 ] ;;
	*) return 1 ;;
	esac
}

echo "== fake agent (difficulty=$DIFFICULTY, uid=$(id -u)) =="

# --- Reference patch must be hidden during the agent phase --------------------
code=$(curl -s -o /dev/null -w '%{http_code}' --unix-socket "$SOCK" http://d/reference/patch)
[ "$code" = 403 ] && ok "reference patch denied on unix socket ($code)" \
	|| bad "reference patch on unix socket returned $code (want 403)"

code=$(curl -s -o /dev/null -w '%{http_code}' "$HTTP/reference/patch")
[ "$code" = 403 ] && ok "reference patch denied on HTTP ($code)" \
	|| bad "reference patch on HTTP returned $code (want 403)"

# The old endpoint name must be gone.
code=$(curl -s -o /dev/null -w '%{http_code}' --unix-socket "$SOCK" http://d/cheating/ground_truth)
[ "$code" = 404 ] && ok "old /cheating/ground_truth removed ($code)" \
	|| bad "/cheating/ground_truth returned $code (want 404)"

# --- Difficulty gate on bencher actions --------------------------------------
for action in build function_test run_poc intent_test; do
	for listener in unix http; do
		code=$([ "$listener" = unix ] && bencher_unix "$action" || bencher_http "$action")
		if action_allowed "$action"; then
			[ "$code" != 403 ] && ok "$action permitted on $listener ($code)" \
				|| bad "$action wrongly blocked on $listener ($code)"
		else
			[ "$code" = 403 ] && ok "$action blocked on $listener ($code)" \
				|| bad "$action NOT blocked on $listener ($code, want 403)"
		fi
	done
done

# --- model must have no supplementary groups ---------------------------------
# A base image's uid-1000 user (ubuntu) carries sudo, adm and more; the fresh
# model user must belong to its own group only.
groups=$(id -G)
if [ "$groups" = "$(id -g)" ]; then
	ok "model has no supplementary groups ($groups)"
else
	bad "model has supplementary groups: $groups"
fi

# --- Privileged admin socket must be unreachable to model --------------------
if curl -s -m 3 --unix-socket "$ADMIN_SOCK" http://d/version >/dev/null 2>&1; then
	bad "admin socket reachable by model"
else
	ok "admin socket unreachable by model"
fi

# --- The daemon's sockets must not be replaceable ----------------------------
# Whoever controls a socket path can answer in the daemon's place, for example
# with a passing grade to the evaluator.
for s in "$SOCK" "$ADMIN_SOCK"; do
	if mv "$s" "$s.moved" 2>/dev/null; then
		mv "$s.moved" "$s" 2>/dev/null
		bad "socket can be moved: $s"
	else
		ok "socket cannot be moved: $s"
	fi
done

# --- Reference patch, hidden tests and PoCs must not be readable -------------
for f in \
	/ssebench/diffs/patch.diff \
	/ssebench/diffs/test.diff \
	/ssebench/diffs/security_test.diff \
	/ssebench/pocs/poc.go \
	/ssebench-repo \
	/reference/patch.diff; do
	if cat "$f" >/dev/null 2>&1 || ls "$f" >/dev/null 2>&1; then
		bad "readable: $f"
	else
		ok "not readable: $f"
	fi
done

# --- Git history must not reveal the fix -------------------------------------
if [ -d "$SOURCE_DIR/.git" ]; then
	n=$(git -C "$SOURCE_DIR" log --oneline 2>/dev/null | wc -l)
	[ "$n" -le 1 ] && ok "git history squashed to $n commit" \
		|| bad "git history has $n commits"
fi

# --- No internet under the restricted egress policy --------------------------
if curl -s -m 5 -o /dev/null https://crates.io 2>/dev/null \
	|| curl -s -m 5 -o /dev/null https://github.com 2>/dev/null; then
	bad "internet reachable under restricted egress"
else
	ok "internet unreachable under restricted egress"
fi

# --- Nor through the daemon's bash tool, where the daemon runs --------------
# In a sidecar run that is the task container, not this one. Prints LEAK when
# the command given succeeds there, SAFE when it fails, and ERROR when the tool
# did not run it.
daemon_probe() {
	out=$(curl -s -m 60 --unix-socket "$SOCK" -X POST "http://d/tool/bash?action=execute" \
		-H 'Content-Type: application/json' \
		-d "{\"command\":\"($1) >/dev/null 2>&1 && echo LEAK || echo SAFE\"}" |
		sed -n 's/.*"stdout":"\([^"]*\)".*/\1/p')
	case "$out" in
	LEAK*) echo LEAK ;;
	SAFE*) echo SAFE ;;
	*) echo ERROR ;;
	esac
}
probe_daemon() {
	case "$(daemon_probe "$1")" in
	SAFE) ok "blocked through the bash tool: $2" ;;
	LEAK) bad "possible through the bash tool: $2" ;;
	*) bad "bash tool probe failed: $2" ;;
	esac
}
for f in /ssebench/diffs/patch.diff /ssebench/diffs/test.diff /ssebench/pocs/poc.go; do
	probe_daemon "cat $f" "read $f"
done
probe_daemon "ls /ssebench-repo" "list /ssebench-repo"
probe_daemon "timeout 5 bash -c '</dev/tcp/github.com/443'" "reach the internet"

# --- The bash tool runs as the agent does, not as the daemon -----------------
# It must have the agent's uid, no supplementary groups (root's group 0 in
# particular), the agent's home and none of the daemon's root-only paths, so
# that git, uv and the toolchains work in it as they do in the agent's shell.
tool_stdout=$(curl -s -m 60 --unix-socket "$SOCK" -X POST "http://d/tool/bash?action=execute" \
	-H 'Content-Type: application/json' \
	-d '{"command":"echo $(id -u) $(id -G) $HOME $USER ${SSE_ADMIN_SOCKET-unset}"}' |
	sed -n 's/.*"stdout":"\([^"]*\)".*/\1/p')
tool_stdout="${tool_stdout%\\n}"
want="$(id -u) $(id -G) $HOME $(id -un) unset"
[ "$tool_stdout" = "$want" ] && ok "bash tool runs as the agent ($tool_stdout)" \
	|| bad "bash tool runs as: '$tool_stdout' (want '$want')"
case " ${tool_stdout#* } " in
*" 0 "*) bad "bash tool has group 0" ;;
*) ok "bash tool has no group 0" ;;
esac

# --- Allowed tooling still works ---------------------------------------------
code=$(curl -s -o /dev/null -w '%{http_code}' --unix-socket "$SOCK" \
	-X POST "http://d/tool/bash?action=execute" \
	-H 'Content-Type: application/json' -d '{"command":"echo hi"}')
[ "$code" = 200 ] && ok "bash tool works ($code)" || bad "bash tool returned $code"

if [ "$fail" -eq 0 ]; then
	echo "== all integrity checks passed =="
else
	echo "== integrity checks FAILED =="
fi
exit "$fail"
