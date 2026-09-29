#!/bin/bash
# Fake agent: runs as the unprivileged `model` user inside a real sandbox
# container and tries every known way to reach information the benchmark must
# withhold. It exits non-zero if any bypass succeeds or any allowed action is
# wrongly blocked.
#
# Usage: fake_agent.sh <difficulty> <source_dir>
#
# Difficulty -> allowed bencher actions (mirrors the daemon gate):
#   build         allowed when difficulty <= 3
#   function_test allowed when difficulty <= 2
#   run_poc       allowed when difficulty <= 1
#   intent_test   allowed when difficulty <= 0

set -u

DIFFICULTY="${1:?usage: fake_agent.sh <difficulty> <source_dir>}"
SOURCE_DIR="${2:?usage: fake_agent.sh <difficulty> <source_dir>}"

SOCK=/tmp/sse.sock
ADMIN_SOCK=/run/ssebench/admin.sock
HTTP=http://localhost:4263

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

# --- Privileged admin socket must be unreachable to model --------------------
if curl -s -m 3 --unix-socket "$ADMIN_SOCK" http://d/version >/dev/null 2>&1; then
	bad "admin socket reachable by model"
else
	ok "admin socket unreachable by model"
fi

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
