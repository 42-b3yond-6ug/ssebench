#!/usr/bin/env bash
set -euo pipefail

DATASET_DIR=$1
RESULTS_DIR="results"
VALIDATOR_DOCKERFILE="Dockerfile"

# docker resource limits
MEMORY_LIMIT="64g"
CPU_LIMIT="64.0"

mkdir -p "$RESULTS_DIR"

for testcase_dir in "$DATASET_DIR"/*/; do
    testcase_name=$(basename "$testcase_dir")

    # lowercase normalized names
    testcase_image="testcase_${testcase_name}"
    validator_image="validator_${testcase_name}"
    testcase_image=$(echo "$testcase_image" | tr '[:upper:]' '[:lower:]')
    validator_image=$(echo "$validator_image" | tr '[:upper:]' '[:lower:]')

    log_file="$RESULTS_DIR/${testcase_name}.log"

    # ---- skip if log already exists ----
    if [[ -f "$log_file" ]]; then
        echo "[SKIP] $testcase_name → log already exists at $log_file"
        continue
    fi

    echo "==============================="
    echo " Processing testcase: $testcase_name"
    echo "==============================="

    # ---- build testcase image ----
    echo "[+] Building testcase image: $testcase_image"
    docker build -t "$testcase_image" "$testcase_dir"

    # ---- build validator image ----
    echo "[+] Building validator image: $validator_image"
    docker build \
        -f "$VALIDATOR_DOCKERFILE" \
        --build-arg TESTCASE_IMAGE="$testcase_image" \
        -t "$validator_image" \
        .

    # ---- run validator ----
    echo "[+] Running validator for $testcase_name"

    rm -f "$log_file"

    container_id=$(docker run \
        --network none \
        --cpus="$CPU_LIMIT" \
        --memory="$MEMORY_LIMIT" \
        --name "validator_run_${testcase_name}" \
        -d "$validator_image"
    )

    docker logs -f "$container_id" | tee "$log_file"

    exit_code=$(docker wait "$container_id")
    echo "Validator exit code: $exit_code" >> "$log_file"

    # ---- cleanup ----
    echo "[+] Cleaning up..."

    docker rm "$container_id" >/dev/null 2>&1 || true
    docker rmi "$validator_image" >/dev/null 2>&1 || true
    docker rmi "$testcase_image" >/dev/null 2>&1 || true

    echo "[✓] Finished testcase: $testcase_name"
done

echo "====================================="
echo " All testcases processed (skipping logged ones)."
echo " Results stored in: $RESULTS_DIR/"
echo "====================================="