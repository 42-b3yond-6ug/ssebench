"""A run whose agent failed and whose model answered no call is an error, not a failed patch."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ssebench.models import Model
from ssebench.models import model as model_module
from ssebench.runner.result import EvaluationResult, RunConfig, model_never_answered
from ssebench.runner.runner import record_results
from ssebench.tasks import LocalTask

TASK = "demo-1"
UNMODIFIED = {"build_success": True, "pov_passed": 0, "pov_total": 1, "func_test_success": True}


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def grade(exit_code: int | None, patch: dict[str, object] | None = None) -> EvaluationResult:
    runtime: dict[str, object] = {"agent_duration": 3, "agent_timeout": False, "evaluator_timeout": False}
    if exit_code is not None:
        runtime["agent_exit_code"] = exit_code
    return EvaluationResult.model_validate({"patch_result": patch or UNMODIFIED, "runtime_result": runtime})


@pytest.mark.parametrize(
    ("exit_code", "spend", "is_error"),
    [(1, 0.0, True), (124, 0.0, True), (1, 0.02, False), (0, 0.0, False), (None, 0.0, False)],
)
def test_only_a_failed_agent_without_spend_is_an_error(exit_code: int | None, spend: float, is_error: bool) -> None:
    assert (model_never_answered(grade(exit_code), spend) is not None) is is_error


def record(
    task: LocalTask,
    tmp_path: Path,
    result: EvaluationResult,
    spend: float,
    settled: Callable[[], float] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluator_file = tmp_path / "result.json"
    _ = evaluator_file.write_text(result.model_dump_json())
    config = RunConfig(agent="claude-code", model="m", mode="sandbox", timeout=60, difficulty=2)
    record_results(task, config, spend, evaluator_file, settled_spend=settled)
    return json.loads(evaluator_file.read_text()), json.loads((tmp_path / "summary.json").read_text())


def test_the_run_is_recorded_as_an_error_with_the_exit_code(task: LocalTask, tmp_path: Path) -> None:
    result, summary = record(task, tmp_path, grade(1), 0.0, lambda: 0.0)

    for record_ in (result, summary):
        assert record_["patch_result"]["status"] == "error"
        assert record_["patch_result"]["pov_passed"] == 0
        assert record_["runtime_result"]["agent_exit_code"] == 1
        assert "the model answered no call" in record_["patch_result"]["error_msg"]


def test_the_grading_message_is_kept(task: LocalTask, tmp_path: Path) -> None:
    patch = {**UNMODIFIED, "error_msg": "PoC failed: poc.bin"}

    result, _ = record(task, tmp_path, grade(1, patch), 0.0, lambda: 0.0)

    assert result["patch_result"]["error_msg"].endswith("; grading said: PoC failed: poc.bin")


def test_spend_that_the_proxy_books_late_keeps_the_grade(task: LocalTask, tmp_path: Path) -> None:
    result, summary = record(task, tmp_path, grade(1), 0.0, lambda: 0.4)

    assert result["patch_result"]["status"] == "failed"
    assert summary["spend"] == 0.4


@pytest.mark.parametrize("settled", [None, lambda: pytest.fail("no spend to wait for")])
def test_a_run_that_uses_no_model_or_whose_agent_succeeded_keeps_its_grade(
    task: LocalTask, tmp_path: Path, settled: Callable[[], float] | None
) -> None:
    result, _ = record(task, tmp_path, grade(1 if settled is None else 0), 0.0, settled)

    assert result["patch_result"]["status"] == "failed"


def test_the_spend_is_awaited_until_the_proxy_books_it(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = iter([0.0, 0.0, 0.3])
    sleeps: list[float] = []
    monkeypatch.setattr(model_module.time, "sleep", sleeps.append)
    proxy = Model.__new__(Model)
    monkeypatch.setattr(Model, "get_spend", lambda self: next(readings))

    assert proxy.settled_spend(15) == 0.3
    assert len(sleeps) == 2


def test_the_wait_for_spend_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    monkeypatch.setattr(model_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(model_module.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    proxy = Model.__new__(Model)
    monkeypatch.setattr(Model, "get_spend", lambda self: 0.0)

    assert proxy.settled_spend(5) == 0.0
    assert now[0] == 5
