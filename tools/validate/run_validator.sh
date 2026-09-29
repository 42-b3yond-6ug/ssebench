#!/usr/bin/env bash
# Validate dataset tasks: build each task's case image, then run validate.py on
# top of it without network access. It checks that the project builds, that the
# PoCs crash before the reference patch and not after it, and that the tests
# behave. Logs go to results/validate/<task>.log.
#
# Usage: run_validator.sh <dataset-dir> [task...]
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <dataset-dir> [task...]" >&2
    exit 2
fi
dataset_dir=$(cd "$1" && pwd)
shift
dataset=$(basename "$dataset_dir")
validator_dir=$(cd "$(dirname "$0")" && pwd)
registry="${SSEBENCH_REGISTRY:-ghcr.io/42-b3yond-6ug/ssebench}"
registry="${registry%/}"
results_dir="results/validate"

# docker resource limits; Docker rejects --cpus above the host's CPU count
MEMORY_LIMIT="64g"
CPU_LIMIT=$(getconf _NPROCESSORS_ONLN)

if [ $# -gt 0 ]; then
    tasks=("$@")
else
    tasks=()
    for dir in "$dataset_dir"/*/; do
        tasks+=("$(basename "$dir")")
    done
fi

mkdir -p "$results_dir"
passed=()
failed=()

for task in "${tasks[@]}"; do
    task_dir="$dataset_dir/$task"
    log_file="$results_dir/$task.log"
    # Same name as the CLI's case image, so either one reuses the other's build.
    case_image=$(echo "$registry/case/$dataset/$task" | tr '[:upper:]' '[:lower:]')
    validator_image=$(echo "$registry/validate/$dataset/$task" | tr '[:upper:]' '[:lower:]')

    echo "==============================="
    echo " Validating $task"
    echo "==============================="

    if [ ! -f "$task_dir/Dockerfile" ]; then
        echo "[!] No task named $task in $dataset_dir" | tee "$log_file"
        failed+=("$task")
        continue
    fi

    built=0
    echo "[+] Building case image $case_image"
    if docker buildx build --load --build-arg SSEBENCH_REGISTRY="$registry" -t "$case_image" "$task_dir"; then
        echo "[+] Building validator image $validator_image"
        docker buildx build --load -f "$validator_dir/Dockerfile" \
            --build-arg TESTCASE_IMAGE="$case_image" -t "$validator_image" "$validator_dir" && built=1
    fi
    if [ "$built" -eq 0 ]; then
        echo "[!] Image build failed for $task" | tee "$log_file"
        failed+=("$task")
        continue
    fi

    echo "[+] Running validator for $task"
    status=0
    docker run --rm --network none --cpus="$CPU_LIMIT" --memory="$MEMORY_LIMIT" "$validator_image" 2>&1 |
        tee "$log_file" || status=$?
    echo "Validator exit code: $status" >>"$log_file"
    docker rmi "$validator_image" >/dev/null 2>&1 || true

    warnings=$(grep -c '\[!\]' "$log_file" || true)
    if [ "$status" -eq 0 ]; then
        echo "[ok] $task ($warnings warning(s); log: $log_file)"
        passed+=("$task")
    else
        echo "[FAILED] $task (exit code $status; log: $log_file)"
        failed+=("$task")
    fi
done

echo "====================================="
echo " ${#passed[@]} task(s) passed, ${#failed[@]} failed. Logs: $results_dir/"
echo " Lines marked [!] in a log are findings to review."
echo "====================================="
if [ ${#failed[@]} -gt 0 ]; then
    printf ' failed: %s\n' "${failed[@]}"
    exit 1
fi
