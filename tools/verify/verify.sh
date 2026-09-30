#!/usr/bin/env bash
# The heavy checks that pull requests do not run in CI, on this machine.
#
#   just verify [options] [part ...]
#
# Parts (all of them by default):
#   kind      Helm chart on a kind cluster with Calico: a pilot task from `ssebench run` and from the web UI
#   agents    every bundled agent runs offline against a stub model, in both modes
#   e2e       the dummy agent on a pilot task in sandbox and sidecar mode, and the integrity bypass tests
#   nix       `nix flake check`
#   images    the base, runtime, litellm, catalog and web UI images (linux/amd64)
#   dataset   `ssebench dataset verify` of the tasks changed since --since
#   binaries  the release binaries for linux/amd64 and linux/arm64, and their versions
#   sdk       the Python SDK against the daemon, in a container
#
# Options:
#   --since REV   base of the dataset part's changed tasks (default: origin/main, or $VERIFY_SINCE)
#   -j N          parts that run at the same time (default: 4, or $VERIFY_JOBS)
#   --prune       remove the images the parts built when they finish (or $VERIFY_PRUNE=1)
#   --list        print the parts and stop
#   -h, --help    print this help
#
# Every part has its own image registry prefix (ssebench-dev/verify-<id>/<part>), Compose project, LiteLLM
# port, kind cluster and kubeconfig, so it runs next to other work on the same Docker daemon. <id> comes from
# the path of this checkout; set VERIFY_ID to change it. Keys are generated for each run, and the
# provider keys are fake: nothing calls a model. A part removes the containers, networks, volumes and cluster
# it created; its images stay as a build cache unless --prune is given. `verify.sh clean` removes
# the images of this checkout's id. Logs are in .verify/<time>/<part>.log, and .verify/latest points at them.
# A part whose tools are missing is skipped with a message; kind, kubectl, helm, jq and go come from nixpkgs
# when nix is available and they are not on PATH.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SELF=$ROOT/tools/verify/verify.sh
cd "$ROOT"

ALL_PARTS=(kind agents e2e nix images dataset binaries sdk)
SKIP_STATUS=77

TASK=gjson-196-bf4efcb
MODEL=claude-sonnet-4-6
COMPOSE_FILE=deploy/compose/docker-compose.yaml

id=${VERIFY_ID:-$(printf %s "$ROOT" | sha1sum | cut -c1-6)}

usage() { sed -n '2,/^set -uo/p' "$SELF" | sed '$d' | sed 's/^# \{0,1\}//'; }
log() { printf '[verify] %s\n' "$*"; }
secret() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
fmt_time() { printf '%dm%02ds' $(($1 / 60)) $(($1 % 60)); }

registry_of() { echo "ssebench-dev/verify-$id/$1"; }
project_of() { echo "ssebench-verify-$id-$1"; }
version() { cat VERSION; }

# ---- tools ---------------------------------------------------------------------------------------------

declare -A NIXPKG=([kind]=kind [kubectl]=kubectl [helm]=kubernetes-helm [jq]=jq [go]=go)

# Put the tools of a part on PATH, from nixpkgs when they are missing; skip the part when one is not available.
need() {
	local tool missing=()
	for tool in "$@"; do
		command -v "$tool" >/dev/null 2>&1 && continue
		if [ -n "${NIXPKG[$tool]:-}" ] && command -v nix >/dev/null 2>&1; then
			local out dir
			if out=$(nix build --no-link --print-out-paths "nixpkgs#${NIXPKG[$tool]}" 2>/dev/null); then
				while IFS= read -r dir; do
					[ -d "$dir/bin" ] && PATH="$dir/bin:$PATH"
				done <<<"$out"
				export PATH
			fi
		fi
		command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
	done
	if [ ${#missing[@]} -gt 0 ]; then
		echo "SKIP: needs ${missing[*]}, which is not installed"
		exit "$SKIP_STATUS"
	fi
}

docker_up() {
	docker info >/dev/null 2>&1 || {
		echo "SKIP: the Docker daemon is not reachable"
		exit "$SKIP_STATUS"
	}
}

# ---- isolation and cleanup -----------------------------------------------------------------------------

# Containers started from an image under this part's registry prefix, which no run of the part should leave.
remove_containers() {
	local prefix=$1
	docker ps -a --format '{{.ID}} {{.Image}}' | awk -v p="$prefix/" 'index($2, p) == 1 { print $1 }' |
		xargs -r docker rm -f >/dev/null 2>&1 || true
}

# Remove what a part created, apart from its images unless --prune.
cleanup_part() {
	local part=$1
	if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
		remove_part_objects "$part"
		if [ "${VERIFY_PRUNE:-}" = 1 ]; then
			prune_images "$(registry_of "$part")"
		fi
	fi
	rm -rf "${KUBECONFIG_DIR:-/nonexistent}"
}

prune_images() {
	docker images --format '{{.Repository}}:{{.Tag}}' | grep -F "$1/" | xargs -r docker rmi >/dev/null 2>&1 || true
}

# The containers, Compose project, network and cluster of a part. The same call clears what an earlier run that
# was killed before it cleaned up left behind.
remove_part_objects() {
	local part=$1 project
	project=$(project_of "$part")
	remove_containers "$(registry_of "$part")"
	docker compose -p "$project" -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
	docker network rm "$project-integrity" >/dev/null 2>&1 || true
	if [ "$part" = kind ] && command -v kind >/dev/null 2>&1; then
		kind delete cluster --name "$project" >/dev/null 2>&1 || true
	fi
}

# The environment of one part: its own registry, Compose project and port, and keys that are only for this run.
isolate() {
	local part=$1 var
	for var in $(compgen -e | grep '^SSEBENCH_' || true); do
		[ "$var" = SSEBENCH_HOME ] || unset "$var"
	done
	unset SSEBENCH_CATALOG
	export SSEBENCH_REGISTRY COMPOSE_PROJECT_NAME LITELLM_PORT LITELLM_BIND LITELLM_MASTER_KEY POSTGRES_PASSWORD
	SSEBENCH_REGISTRY=$(registry_of "$part")
	COMPOSE_PROJECT_NAME=$(project_of "$part")
	LITELLM_PORT=${VERIFY_PORT:?}
	LITELLM_BIND=127.0.0.1
	LITELLM_MASTER_KEY=sk-$(secret)
	POSTGRES_PASSWORD=$(secret)
	export ANTHROPIC_API_KEY=sk-not-a-real-key OPENAI_API_KEY=sk-not-a-real-key GOOGLE_API_KEY=not-a-real-key
	export SSEBENCH_INTEGRITY_NETWORK="$COMPOSE_PROJECT_NAME-integrity"
}

# Unique results directory names: a run ID is used once.
run_id() { echo "verify-$1-$(date -u +%Y%m%d-%H%M%S)-$$"; }

# ---- parts ---------------------------------------------------------------------------------------------

build_base_image() { make -C images/base-images "$@" SSEBENCH_REGISTRY="$SSEBENCH_REGISTRY"; }

# Run the commands of the lines on stdin, "name<TAB>command", with at most $1 at a time, each logging to its own file.
bounded() {
	local limit=$1 name cmd failed=0 pids=() names=() i
	while IFS=$'\t' read -r name cmd; do
		[ -n "$name" ] || continue
		while [ "$(jobs -rp | wc -l)" -ge "$limit" ]; do wait -n || true; done
		echo "==> $name: $cmd"
		(eval "$cmd") >"$LOGDIR/$PART.$name.log" 2>&1 &
		pids+=("$!")
		names+=("$name")
	done
	for i in "${!pids[@]}"; do
		if ! wait "${pids[$i]}"; then
			echo "FAILED: ${names[$i]}; log: $LOGDIR/$PART.${names[$i]}.log" >&2
			tail -n 25 "$LOGDIR/$PART.${names[$i]}.log" >&2
			failed=1
		else
			echo "ok: ${names[$i]}"
		fi
	done
	return "$failed"
}

part_e2e() {
	need docker jq uv
	docker_up
	build_base_image generic-go

	local sandbox
	sandbox=$(run_id sandbox)
	uv run ssebench run --model "$MODEL" --agent dummy --task "$TASK" --mode sandbox --local datasets/pilot --run-id "$sandbox"
	local result="results/$TASK/$MODEL/dummy/$sandbox/result.json"
	jq . "$result"
	# The unpatched project must build and its PoC must still fail.
	jq -e '.patch_result.build_success and .patch_result.pov_total > 0 and .patch_result.pov_passed == 0' "$result"

	uv run python tests/integrity/test_bypass.py
	SSEBENCH_SMOKE_TASK=$TASK SSEBENCH_SMOKE_MODEL=$MODEL tests/e2e/smoke.sh sidecar
	uv run python tests/integrity/test_bypass.py --mode sidecar
}

part_sdk() {
	need docker
	docker_up
	local image="$SSEBENCH_REGISTRY/sdk-integration:verify"
	docker build -f sdk/tests/integration/Dockerfile -t "$image" .
	docker run --rm "$image"
}

part_kind() {
	need docker kind kubectl helm jq uv curl
	docker_up
	local v cluster=$COMPOSE_PROJECT_NAME
	v=$(version)
	KUBECONFIG_DIR=$LOGDIR/kind
	mkdir -p "$KUBECONFIG_DIR"
	export KUBECONFIG="$KUBECONFIG_DIR/kubeconfig"
	# The versions the helm workflow pins.
	local calico chart=deploy/helm/ssebench
	calico=$(sed -n 's/^  CALICO_VERSION: *//p' .github/workflows/helm.yml)
	[ -n "$calico" ] || { echo "no CALICO_VERSION in .github/workflows/helm.yml"; return 1; }

	helm lint "$chart" --strict
	local values
	for values in "$chart"/ci/*.yaml; do helm lint "$chart" --strict --values "$values"; done

	# The cluster comes up while the images build.
	(
		set -e
		# Calico enforces NetworkPolicy; kind's default network plugin does not.
		kind create cluster --name "$cluster" --config deploy/k8s/kind.yaml --kubeconfig "$KUBECONFIG" --wait 0
		kubectl apply -f "https://raw.githubusercontent.com/projectcalico/calico/v${calico}/manifests/calico.yaml"
		kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
		kubectl wait --for=condition=Ready nodes --all --timeout=300s
		docker pull postgres:16
	) >"$LOGDIR/kind.cluster.log" 2>&1 &
	local cluster_pid=$!

	printf '%s\t%s\n' \
		litellm "docker build -f images/litellm/Dockerfile -t $SSEBENCH_REGISTRY/litellm:$v ." \
		catalog "docker build -f catalog/Dockerfile --build-arg VERSION=$v -t $SSEBENCH_REGISTRY/catalog:$v ." \
		webui "docker build -f webui/Dockerfile --build-arg VERSION=$v -t $SSEBENCH_REGISTRY/webui:$v ." |
		bounded 3 || { kill "$cluster_pid" 2>/dev/null; return 1; }

	# A run on the local Docker daemon builds the case, tool and agent layers of the reference agent.
	build_base_image generic-go
	local baseline
	baseline=$(run_id docker-baseline)
	uv run ssebench run --agent reference --task "$TASK" --mode sandbox --local datasets/pilot --run-id "$baseline"
	jq -e '.patch_result.status == "passed"' "results/$TASK/none/reference/$baseline/result.json"

	if ! wait "$cluster_pid"; then
		echo "The cluster did not come up; log: $LOGDIR/kind.cluster.log"
		tail -n 40 "$LOGDIR/kind.cluster.log"
		return 1
	fi
	kind load docker-image --name "$cluster" \
		"$SSEBENCH_REGISTRY/litellm:$v" "$SSEBENCH_REGISTRY/catalog:$v" "$SSEBENCH_REGISTRY/webui:$v" \
		"$SSEBENCH_REGISTRY/agent-reference/$TASK:$v" postgres:16

	kubectl create namespace ssebench-runs
	kubectl create namespace ssebench
	# Fake keys: the reference agent makes no model call.
	kubectl -n ssebench create secret generic provider-keys \
		--from-literal=ANTHROPIC_API_KEY=sk-not-a-real-key \
		--from-literal=OPENAI_API_KEY=sk-not-a-real-key \
		--from-literal=GOOGLE_API_KEY=not-a-real-key
	helm install ssebench "$chart" --namespace ssebench --wait --timeout 10m \
		--set image.registry="$SSEBENCH_REGISTRY" --set image.pullPolicy=Never \
		--set runs.imagePullPolicy=Never --set runs.namespace=ssebench-runs \
		--set 'litellm.providerKeySecrets={provider-keys}'

	local status=0
	IMAGE_PULL_POLICY=Never PROBE_IMAGE="$SSEBENCH_REGISTRY/litellm:$v" tests/helm/smoke.sh || status=$?
	if [ "$status" -ne 0 ]; then
		kubectl get pods,jobs,networkpolicy -A -o wide || true
		kubectl -n ssebench describe pods || true
		local deploy
		for deploy in litellm catalog webui; do
			kubectl -n ssebench logs "deploy/ssebench-$deploy" --tail=100 || true
		done
		kubectl -n ssebench-runs describe pods || true
	fi
	return "$status"
}

part_nix() {
	need nix
	nix flake check -L
}

part_agents() {
	need docker uv
	docker_up
	build_base_image generic-go
	uv run pytest tests/agents -m agents -q
}

part_images() {
	need docker
	docker_up
	local v r=$SSEBENCH_REGISTRY
	v=$(version)
	printf '%s\t%s\n' \
		base-generic-c "docker build -f images/base-images/generic-c/Dockerfile -t $r/base-generic-c:$v images/base-images" \
		base-generic-go "docker build -f images/base-images/generic-go/Dockerfile -t $r/base-generic-go:$v images/base-images" \
		base-generic-rust "docker build -f images/base-images/generic-rust/Dockerfile -t $r/base-generic-rust:$v images/base-images" \
		runtime "docker build -f images/runtime/Dockerfile --build-arg VERSION=$v -t $r/runtime:$v ." \
		litellm "docker build -f images/litellm/Dockerfile -t $r/litellm:$v ." \
		catalog "docker build -f catalog/Dockerfile --build-arg VERSION=$v -t $r/catalog:$v ." \
		webui "docker build -f webui/Dockerfile --build-arg VERSION=$v -t $r/webui:$v ." |
		bounded "${VERIFY_BUILD_JOBS:-4}"
}

part_binaries() {
	need docker go
	docker_up
	local v out=$LOGDIR/binaries arch
	v=$(version)
	rm -rf "$out"
	mkdir -p "$out/dist"
	# The daemon and the entrypoint cross-compile on this platform (see images/runtime/Dockerfile), so each
	# architecture is its own build and needs no emulation.
	for arch in amd64 arm64; do
		docker buildx build -f images/runtime/Dockerfile --platform "linux/$arch" --build-arg VERSION="$v" \
			--provenance=false --sbom=false --output "type=local,dest=$out/runtime-$arch" .
		cp "$out/runtime-$arch/ssebench/ssebench-daemon" "$out/dist/ssebench-daemon-linux-$arch"
		cp "$out/runtime-$arch/usr/local/bin/entrypoint" "$out/dist/ssebench-entrypoint-linux-$arch"
		CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -C catalog -trimpath -ldflags="-s -w -X main.version=$v" \
			-o "$out/dist/ssebench-catalog-linux-$arch" ./cmd/ssebench-catalog
		CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -C webui/pty-proxy -trimpath -ldflags="-s -w -X main.version=$v" \
			-o "$out/dist/ssebench-pty-proxy-linux-$arch" .
	done
	chmod +x "$out"/dist/*
	(cd "$out/dist" && sha256sum -- * >SHA256SUMS && cat SHA256SUMS)
	local bin reported status=0
	for bin in "$out"/dist/*-linux-amd64; do
		# Each program ends its --version line with the version.
		reported=$("$bin" --version)
		echo "$bin: $reported"
		case "$reported" in
		*" $v") ;;
		*)
			echo "$bin reports '$reported', not $v"
			status=1
			;;
		esac
	done
	return "$status"
}

part_dataset() {
	need docker jq uv make
	docker_up
	local since=${VERIFY_SINCE:-origin/main} tasks bases
	git rev-parse --verify --quiet "$since^{commit}" >/dev/null || {
		echo "$since is not a commit; fetch it or pass --since REV"
		return 1
	}
	tasks=$(uv run ssebench dataset verify --list --changed-since "$since") || return 1
	echo "Changed since $since:"
	jq -r '.[] | "  \(.task) on \(.base)"' <<<"$tasks"
	if [ "$(jq length <<<"$tasks")" = 0 ]; then
		echo "No task changed; nothing to verify."
		return 0
	fi
	# The case images build on the base images of this checkout.
	mapfile -t bases < <(jq -r '.[].base | split(":")[0] | split("@")[0] | ltrimstr("base-")' <<<"$tasks" | sort -u)
	build_base_image "${bases[@]}"
	uv run ssebench dataset verify --changed-since "$since" --output "$LOGDIR/dataset" \
		--jobs "${VERIFY_DATASET_JOBS:-2}" --retries 1
}

# ---- one part ------------------------------------------------------------------------------------------

# The body of a part's own process: isolate it, run it, clean up, and record the outcome.
run_part() {
	local part=$1 rc start=$SECONDS
	PART=$part
	isolate "$part"
	# The subshell cleans up when the signal reaches it; this shell then records the interrupted outcome.
	trap 'printf "143 %s\n" "$((SECONDS - start))" >"$LOGDIR/$part.status"; exit 143' TERM INT HUP
	(
		trap 'cleanup_part "$PART"' EXIT
		# A subshell resets the parent's traps; the exit status makes the EXIT trap run on a signal.
		trap 'exit 143' TERM INT HUP
		docker info >/dev/null 2>&1 && remove_part_objects "$PART"
		"part_$PART"
	) >"$LOGDIR/$part.log" 2>&1
	rc=$?
	printf '%s %s\n' "$rc" "$((SECONDS - start))" >"$LOGDIR/$part.status"
	exit "$rc"
}

# ---- main ----------------------------------------------------------------------------------------------

free_port() {
	local port
	for port in $(shuf -i 4100-4999 -n 400); do
		[[ " ${USED_PORTS[*]:-} " == *" $port "* ]] && continue
		(exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && continue
		USED_PORTS+=("$port")
		echo "$port"
		return 0
	done
	return 1
}

list_parts() {
	printf '%s\n' "${ALL_PARTS[@]}"
}

clean_images() {
	local part
	for part in "${ALL_PARTS[@]}"; do prune_images "$(registry_of "$part")"; done
	log "removed the images under ssebench-dev/verify-$id/"
}

main() {
	local parts=() jobs=${VERIFY_JOBS:-4} since=${VERIFY_SINCE:-origin/main}
	while [ $# -gt 0 ]; do
		case "$1" in
		-h | --help) usage; return 0 ;;
		--list) list_parts; return 0 ;;
		--prune) export VERIFY_PRUNE=1 ;;
		--since) since=${2:?--since needs a revision}; shift ;;
		-j | --jobs) jobs=${2:?-j needs a number}; shift ;;
		clean) clean_images; return 0 ;;
		-*) echo "unknown option $1" >&2; usage >&2; return 2 ;;
		*)
			[[ " ${ALL_PARTS[*]} " == *" $1 "* ]] || { echo "unknown part '$1' (${ALL_PARTS[*]})" >&2; return 2; }
			parts+=("$1")
			;;
		esac
		shift
	done
	[ ${#parts[@]} -gt 0 ] || parts=("${ALL_PARTS[@]}")
	export VERIFY_SINCE=$since

	mkdir -p "$ROOT/.verify"
	exec 9>"$ROOT/.verify/lock"
	flock -n 9 || { echo "another just verify is running in this checkout; use VERIFY_ID to run a second one" >&2; return 1; }

	if [ -f .env ] && grep -Eq '^(ANTHROPIC|OPENAI|GOOGLE)_API_KEY=.+' .env; then
		log "warning: .env holds provider keys. They reach only the proxy containers that the parts start, which make no model call."
	fi
	command -v uv >/dev/null 2>&1 && uv sync --locked --quiet

	LOGDIR=$ROOT/.verify/$(date +%Y%m%d-%H%M%S)
	export LOGDIR
	mkdir -p "$LOGDIR"
	ln -sfn "$LOGDIR" "$ROOT/.verify/latest"
	log "id $id, parts: ${parts[*]}, $jobs at a time; logs in $LOGDIR"

	local part pids=() USED_PORTS=() launcher=()
	local -A part_of=()
	command -v setsid >/dev/null 2>&1 && launcher=(setsid)
	trap 'interrupt' INT TERM
	interrupt() {
		log "interrupted; stopping the parts and cleaning up"
		local pid
		for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true; done
		wait
		summarize "${parts[@]}"
		exit 130
	}

	# Wait for one part to end, and say so.
	reap() {
		local done_pid
		wait -n -p done_pid || true
		[ -z "${done_pid:-}" ] || log "finished ${part_of[$done_pid]} ($(fmt_time "$(part_seconds "${part_of[$done_pid]}")"))"
	}

	local t0=$SECONDS
	for part in "${parts[@]}"; do
		while [ "$(jobs -rp | wc -l)" -ge "$jobs" ]; do reap; done
		local port
		port=$(free_port) || { echo "no free port for $part" >&2; return 1; }
		log "start $part (LiteLLM port $port)"
		VERIFY_PORT=$port "${launcher[@]}" "$SELF" --run-part "$part" >/dev/null 2>&1 &
		pids+=("$!")
		part_of[$!]=$part
	done
	while [ "$(jobs -rp | wc -l)" -gt 0 ]; do reap; done
	summarize "${parts[@]}"
	local rc=$?
	log "total $(fmt_time $((SECONDS - t0)))"
	return "$rc"
}

part_seconds() { awk '{ print $2 }' "$LOGDIR/$1.status" 2>/dev/null || echo 0; }

summarize() {
	local part rc secs failed=0 line status
	echo
	printf '%-10s %-6s %8s  %s\n' PART RESULT TIME LOG
	for part in "$@"; do
		if [ -f "$LOGDIR/$part.status" ]; then
			read -r rc secs <"$LOGDIR/$part.status"
			case "$rc" in
			0) status=PASS ;;
			"$SKIP_STATUS") status=SKIP ;;
			*) status=FAIL; failed=1 ;;
			esac
		else
			rc=- secs=0 status=FAIL
			failed=1
		fi
		printf '%-10s %-6s %8s  %s\n' "$part" "$status" "$(fmt_time "$secs")" "$LOGDIR/$part.log"
		if [ "$status" = SKIP ]; then
			line=$(grep -m1 '^SKIP:' "$LOGDIR/$part.log" 2>/dev/null) && printf '           %s\n' "$line"
		elif [ "$status" = FAIL ] && [ -f "$LOGDIR/$part.log" ]; then
			printf '           last lines:\n'
			tail -n 5 "$LOGDIR/$part.log" | sed 's/^/             /'
		fi
	done
	[ "$failed" = 0 ] && echo "verify: passed" || echo "verify: FAILED"
	return "$failed"
}

if [ "${1:-}" = --run-part ]; then
	run_part "$2"
fi
main "$@"
