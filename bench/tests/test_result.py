"""The grade status of a run: an ungraded run is an error, never a success."""

import pytest

from ssebench.runner.result import EvaluationResult, PatchResult

RUNTIME = '"runtime_result": {"agent_duration": 0, "agent_timeout": false, "evaluator_timeout": false}'


def test_no_result_from_the_container_is_an_error() -> None:
    # What the runner records when result.json is empty.
    assert PatchResult(error_msg="No result: evaluator did not produce output").status == "error"


@pytest.mark.parametrize(
    ("patch_result", "status"),
    [
        ('{"error_msg": "Timeout (3600s)"}', "error"),
        ('{"error_msg": "Exception: daemon unreachable"}', "error"),
        ('{"build_success": false, "error_msg": "Build failed"}', "failed"),
        ('{"build_success": true, "pov_passed": 0, "pov_total": 1}', "failed"),
        ('{"build_success": true, "func_test_success": true, "intent_test_success": false}', "failed"),
        ('{"build_success": true, "pov_passed": 2, "pov_total": 2, "func_test_success": true}', "passed"),
    ],
)
def test_status_is_derived_when_result_json_has_none(patch_result: str, status: str) -> None:
    result = EvaluationResult.model_validate_json(f'{{"patch_result": {patch_result}, {RUNTIME}}}')
    assert result.patch_result.status == status


def test_status_from_the_evaluator_is_kept() -> None:
    result = EvaluationResult.model_validate_json(
        f'{{"patch_result": {{"status": "error", "error_msg": "No check ran"}}, {RUNTIME}}}'
    )
    assert result.patch_result.status == "error"


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        _ = PatchResult.model_validate({"status": "success"})
