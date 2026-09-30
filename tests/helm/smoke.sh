#!/usr/bin/env bash
# Smoke test of the Helm chart on a cluster whose network plugin enforces
# NetworkPolicy: the `reference` agent must pass one pilot task, first from
# `ssebench run` and then from the web UI, both on the Kubernetes backend.
#
# Usage: tests/helm/smoke.sh
#
# The chart must be installed already (deploy/helm/ssebench, with the web UI in
# hosted mode, which is the default), and the prebuilt reference image of the
# task and the chart's images must be on the nodes. Needs kubectl, helm, curl, jq
# and uv. Settings, all optional except the registry:
#
#   SSEBENCH_REGISTRY  registry of the prebuilt images (required)
#   RELEASE            the Helm release (default ssebench)
#   NAMESPACE          the release's namespace (default ssebench)
#   RUNS_NAMESPACE     the runs' namespace (default ssebench-runs)
#   CHART              the chart, for `helm upgrade` (default deploy/helm/ssebench)
#   IMAGE_PULL_POLICY  pull policy of the run pods (default IfNotPresent)
#   PROBE_IMAGE        an image with python3, for the network policy check; without
#                      it the check is skipped
set -euo pipefail

cd "$(dirname "$0")/../.."

: "${SSEBENCH_REGISTRY:?SSEBENCH_REGISTRY is not set}"
release="${RELEASE:-ssebench}"
ns="${NAMESPACE:-ssebench}"
runs_ns="${RUNS_NAMESPACE:-ssebench-runs}"
chart="${CHART:-deploy/helm/ssebench}"
task="${SSEBENCH_SMOKE_TASK:-gjson-196-bf4efcb}"

# The chart names its objects after the release, plus the chart's name unless the release has it.
case "$release" in
*ssebench*) name="$release" ;;
*) name="$release-ssebench" ;;
esac

pids=()
cleanup() {
	for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

step() { printf '\n== %s\n' "$*"; }
fail() { echo "helm smoke test: $*" >&2; exit 1; }

# Forward a service's port to a free local port, and set the variable $3 to that port. It runs in this
# shell, not in a command substitution, so that the trap can stop the forward.
forward() {
	local svc=$1 port=$2 log
	log=$(mktemp)
	kubectl -n "$ns" port-forward "svc/$svc" ":$port" >"$log" 2>&1 &
	pids+=("$!")
	for _ in $(seq 1 50); do
		if grep -q '^Forwarding from 127.0.0.1:' "$log"; then
			printf -v "$3" '%s' "$(sed -n 's/^Forwarding from 127.0.0.1:\([0-9]*\) .*/\1/p' "$log" | head -n 1)"
			return 0
		fi
		sleep 0.2
	done
	cat "$log" >&2
	fail "no port-forward to $svc"
}

step "The release is up"
kubectl -n "$ns" rollout status "statefulset/$name-litellm-db" --timeout=300s
for component in litellm catalog webui; do
	kubectl -n "$ns" rollout status "deployment/$name-$component" --timeout=300s
done

step "Only the web UI and the runs reach the proxy"
if [ -n "${PROBE_IMAGE:-}" ]; then
	probe="import urllib.request as u
try:
    u.urlopen('http://$name-litellm.$ns.svc:4000/health/liveliness', timeout=5)
    print('REACHED')
except Exception as e:
    print('BLOCKED')"
	kubectl -n default delete pod ssebench-policy-probe --ignore-not-found --wait=true >/dev/null
	kubectl -n default run ssebench-policy-probe --image="$PROBE_IMAGE" --image-pull-policy="${IMAGE_PULL_POLICY:-IfNotPresent}" \
		--restart=Never --command -- python3 -c "$probe"
	for _ in $(seq 1 60); do
		phase=$(kubectl -n default get pod ssebench-policy-probe -o jsonpath='{.status.phase}')
		[ "$phase" = Succeeded ] || [ "$phase" = Failed ] && break
		sleep 2
	done
	verdict=$(kubectl -n default logs ssebench-policy-probe)
	kubectl -n default delete pod ssebench-policy-probe --wait=false >/dev/null
	[ "$verdict" = BLOCKED ] || fail "a pod outside the release reached the proxy: '$verdict'"
else
	echo "PROBE_IMAGE is not set; skipped"
fi

step "ssebench run on the Kubernetes backend"
forward "$name-litellm" 4000 proxy_port
master_key=$(kubectl -n "$ns" get secret "$name-auth" -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)
run_id="helm-smoke-$(date -u +%Y%m%d-%H%M%S)-$$"
(
	export SSEBENCH_BACKEND=kubernetes SSEBENCH_PREBUILT=1
	export SSEBENCH_K8S_NAMESPACE="$runs_ns" SSEBENCH_K8S_PROXY_NAMESPACE="$ns"
	export SSEBENCH_K8S_PROXY_URL="http://$name-litellm.$ns.svc:4000" SSEBENCH_K8S_PROXY_HOST_URL="http://127.0.0.1:$proxy_port"
	export SSEBENCH_K8S_PROXY_SELECTOR="app.kubernetes.io/name=litellm,app.kubernetes.io/instance=$release"
	export SSEBENCH_K8S_IMAGE_PULL_POLICY="${IMAGE_PULL_POLICY:-IfNotPresent}"
	export LITELLM_MASTER_KEY="$master_key"
	uv run ssebench run --agent reference --task "$task" --local datasets/pilot --run-id "$run_id"
)
result="results/$task/none/reference/$run_id/result.json"
jq -e '.patch_result.status == "passed"' "$result" >/dev/null || { jq . "$result" >&2; fail "the reference agent did not pass $task"; }
echo "ssebench run: $task passed"

step "The web UI is a read-only viewer"
token=$(kubectl -n "$ns" get secret "$name-auth" -o jsonpath='{.data.SSEBENCH_WEBUI_TOKEN}' | base64 -d)
forward "$name-webui" 3001 webui_port
api() { curl -sS -H "Authorization: Bearer $token" "$@"; }
launch="{\"task\":\"$task\",\"agent\":\"reference\",\"mode\":\"sandbox\",\"source\":\"remote\"}"

[ "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$webui_port/api/health")" = 401 ] || fail "the web UI answers without its token"
api "http://127.0.0.1:$webui_port/api/health" | jq -e '.backend == "kubernetes" and .hosted == true' >/dev/null || fail "the web UI is not hosted on the kubernetes backend"
code=$(api -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d "$launch" "http://127.0.0.1:$webui_port/api/launch")
[ "$code" = 403 ] || fail "a hosted web UI answered a launch with $code, not 403"
echo "launch refused with 403"

step "A launch from the web UI"
kill "${pids[-1]}" 2>/dev/null || true
unset 'pids[-1]'
helm upgrade "$release" "$chart" -n "$ns" --reuse-values --set webui.hosted=false --wait --timeout 5m
forward "$name-webui" 3001 webui_port
launch_id=$(api -X POST -H 'Content-Type: application/json' -d "$launch" "http://127.0.0.1:$webui_port/api/launch" | jq -re .launch_id)
echo "launched $launch_id"
for _ in $(seq 1 120); do
	available=$(api "http://127.0.0.1:$webui_port/api/containers/$launch_id/result" 2>/dev/null | jq -r '.available // false' 2>/dev/null || echo false)
	[ "$available" = true ] && break
	sleep 5
done
[ "$available" = true ] || { kubectl -n "$runs_ns" get jobs,pods >&2; fail "the launched run has no result after 10 minutes"; }
api "http://127.0.0.1:$webui_port/api/containers/$launch_id/result" | jq -e '.patch_result.status == "passed"' >/dev/null ||
	fail "the run launched from the web UI did not pass $task"
echo "web UI launch: $task passed"

step "Clean up the launched run"
api -X POST "http://127.0.0.1:$webui_port/api/containers/$launch_id/stop" >/dev/null
api -X POST "http://127.0.0.1:$webui_port/api/containers/$launch_id/remove" >/dev/null
for _ in $(seq 1 30); do
	[ -z "$(kubectl -n "$runs_ns" get jobs -o name)" ] && break
	sleep 2
done
[ -z "$(kubectl -n "$runs_ns" get jobs -o name)" ] || fail "the runs' namespace still has Jobs"

echo
echo "helm smoke test passed"
