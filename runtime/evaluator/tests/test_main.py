"""Tests for the evaluator's result: an ungraded run is an error, never a success."""

import asyncio
import importlib.util
import threading
from pathlib import Path
from types import ModuleType

import pytest
from sse.grading import PatchResult as SDKPatchResult


def load_evaluator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ssebench_evaluator_main", Path(__file__).parents[1] / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluator = load_evaluator()


def grade_with(result: SDKPatchResult):
    return lambda: result


def test_passing_checks_are_passed() -> None:
    sdk = SDKPatchResult(
        build_success=True, pov_passed=1, pov_total=1, func_test_success=True, intent_test_success=True
    )
    result, timed_out = asyncio.run(evaluator.run_grading(10, grade_with(sdk)))
    assert result.status == "passed"
    assert not timed_out


def test_a_failed_check_is_failed() -> None:
    sdk = SDKPatchResult(build_success=True, pov_passed=0, pov_total=1, error_msg="PoC failed: /ssebench/pocs/poc.go")
    result, _ = asyncio.run(evaluator.run_grading(10, grade_with(sdk)))
    assert result.status == "failed"
    assert result.error_msg == "PoC failed: /ssebench/pocs/poc.go"


def test_no_check_ran_is_an_error() -> None:
    result, timed_out = asyncio.run(evaluator.run_grading(10, grade_with(SDKPatchResult())))
    assert result.status == "error"
    assert result.error_msg == "No check ran"
    assert not timed_out


def test_an_exception_is_an_error() -> None:
    def grade() -> SDKPatchResult:
        raise RuntimeError("daemon unreachable")

    result, timed_out = asyncio.run(evaluator.run_grading(10, grade))
    assert result.status == "error"
    assert result.error_msg == "Exception: daemon unreachable"
    assert result.build_success is None
    assert not timed_out


def test_a_timeout_is_an_error() -> None:
    release = threading.Event()

    def grade() -> SDKPatchResult:
        _ = release.wait(10)
        return SDKPatchResult(build_success=True)

    async def run():
        # asyncio.run waits for the grading thread, so release it first.
        try:
            return await evaluator.run_grading(0.05, grade)
        finally:
            release.set()

    result, timed_out = asyncio.run(run())
    assert result.status == "error"
    assert result.error_msg == "Timeout (0.05s)"
    assert timed_out


@pytest.mark.parametrize("status", ["passed", "failed", "error"])
def test_status_is_written_to_result_json(status: str) -> None:
    result = evaluator.EvaluationResult(
        patch_result=evaluator.PatchResult(status=status),
        runtime_result=evaluator.RuntimeResult(agent_duration=0, agent_timeout=False, evaluator_timeout=False),
    )
    assert f'"status":"{status}"' in result.model_dump_json()


@pytest.mark.parametrize(("value", "status"), [("0", 0), ("1", 1), ("124", 124), ("", None), ("x", None)])
def test_the_agents_exit_status_comes_from_the_entrypoint(
    monkeypatch: pytest.MonkeyPatch, value: str, status: int | None
) -> None:
    monkeypatch.setenv("AGENT_EXIT_STATUS", value)
    assert evaluator.agent_exit_status() == status


def test_no_exit_status_from_an_entrypoint_that_predates_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_EXIT_STATUS", raising=False)
    assert evaluator.agent_exit_status() is None
