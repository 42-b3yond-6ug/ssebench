#!/usr/bin/env bash
# End-to-end smoke run: the dummy agent on one pilot task, then a check of the
# grade. The dummy agent changes nothing, so the project must build and its PoC
# must still crash.
#
# Usage: tests/e2e/smoke.sh [sandbox|sidecar]
#
# Needs Docker, jq, a .env with the proxy secrets (just setup) and the task's
# base image (make -C images/base-images generic-go). It starts the LiteLLM
# proxy if needed and leaves it running. Override the task or model with
# SSEBENCH_SMOKE_TASK and SSEBENCH_SMOKE_MODEL.
set -euo pipefail

mode="${1:-sandbox}"
task="${SSEBENCH_SMOKE_TASK:-gjson-196-bf4efcb}"
model="${SSEBENCH_SMOKE_MODEL:-claude-sonnet-4-6}"

cd "$(dirname "$0")/../.."

uv run ssebench run --model "$model" --agent dummy --task "$task" --mode "$mode" --local datasets/pilot

result="results/$task/$model/dummy/result.json"
summary="results/$task-dummy-$model.json"
jq . "$result"
jq -e '.patch_result.build_success and .patch_result.pov_total > 0 and .patch_result.pov_passed == 0' "$result" >/dev/null ||
	{ echo "smoke run ($mode): unexpected grade in $result" >&2; exit 1; }
jq -e --arg mode "$mode" '.config.mode == $mode' "$summary" >/dev/null ||
	{ echo "smoke run ($mode): $summary does not record mode $mode" >&2; exit 1; }
echo "smoke run ($mode) passed"
