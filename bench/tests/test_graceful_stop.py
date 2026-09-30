"""Stopping a kept container after grading ends the run normally; the same status without a grade is an error."""

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ssebench.agents import Agent
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner
from ssebench.runner.runner import stopped_after_grading
from ssebench.tasks import LocalTask

TASK = "demo-1"
GRADE = {
    "patch_result": {"build_success": True, "pov_passed": 0, "pov_total": 1, "func_test_success": True},
    "runtime_result": {"agent_duration": 3, "agent_timeout": False, "evaluator_timeout": False},
}


class Container:
    """A container whose `docker run` writes the grade if it `graded`, then exits with `status`."""

    def __init__(self, status: int, graded: bool) -> None:
        self.status = status
        self.graded = graded

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["docker", "run"]:
            if self.graded:
                result = Path("results") / TASK / "none" / "dummy" / "result.json"
                _ = result.write_text(json.dumps(GRADE))
            if self.status:
                raise subprocess.CalledProcessError(self.status, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def run(task: LocalTask, container: Container, keep_container: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(subprocess, "run", container)
    monkeypatch.chdir(tmp_path)
    runner = BenchmarkSandboxRunner(NoModel(), Agent("dummy", task_name=task.name), task, 60, 2, keep_container)
    runner.sandbox_image = "registry.test/agent-image"
    runner.run()


def errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.parametrize("status", [143, 137])
def test_a_stop_after_grading_is_not_an_error(
    status: int, task: LocalTask, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    run(task, Container(status, graded=True), True, monkeypatch, tmp_path)

    assert errors(caplog) == []
    assert f"The kept container was stopped after grading (exit status {status})" in caplog.messages
    summary = json.loads((tmp_path / "results" / f"{TASK}-dummy-none.json").read_text())
    assert summary["patch_result"]["build_success"] is True
    assert summary["runtime_result"]["agent_duration"] == 3


def test_a_clean_exit_after_grading_is_not_an_error(
    task: LocalTask, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    run(task, Container(0, graded=True), True, monkeypatch, tmp_path)

    assert errors(caplog) == []


@pytest.mark.parametrize(
    ("status", "graded", "keep_container"),
    [
        (143, False, True),  # stopped before the grade was written
        (137, False, True),
        (1, True, True),  # a failure, not a stop
        (2, True, True),
        (143, True, False),  # not kept alive, so nothing waits to be stopped
    ],
)
def test_any_other_non_zero_exit_is_an_error(
    status: int,
    graded: bool,
    keep_container: bool,
    task: LocalTask,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run(task, Container(status, graded), keep_container, monkeypatch, tmp_path)

    [message, *_] = errors(caplog)
    assert message == f"Agent container stopped with a non-zero exit status: {status}"
    assert (tmp_path / "results" / f"{TASK}-dummy-none.json").is_file()


@pytest.mark.parametrize(
    ("status", "keep_container", "grade", "expected"),
    [
        (143, True, "{}", True),
        (137, True, "{}", True),
        (143, True, "", False),
        (1, True, "{}", False),
        (0, True, "{}", False),
        (143, False, "{}", False),
    ],
)
def test_stopped_after_grading(status: int, keep_container: bool, grade: str, expected: bool, tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    _ = result.write_text(grade)

    assert stopped_after_grading(status, keep_container, result) is expected
