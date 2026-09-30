"""`ssebench run --backend` and `--prebuilt`, and the settings that stand for them."""

import argparse
from collections.abc import Callable
from pathlib import Path

import pytest

from ssebench import stack
from ssebench.backends import DockerBackend
from ssebench.cli import cli
from ssebench.runner import BenchmarkSandboxRunner
from ssebench.runner.reference import REFERENCE_AGENT
from ssebench.tasks import LocalTask

TASK = "demo-1"


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def run_args(local: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "model": None,
        "agent": REFERENCE_AGENT,
        "task": TASK,
        "local": str(local),
        "catalog": "",
        "mode": "sandbox",
        "tool_layer": None,
        "timeout": 60,
        "difficulty": 2,
        "keep_container": False,
        "egress": "restricted",
    }
    return argparse.Namespace(**(defaults | overrides))


@pytest.fixture
def runners(monkeypatch: pytest.MonkeyPatch) -> list[BenchmarkSandboxRunner]:
    made: list[BenchmarkSandboxRunner] = []
    monkeypatch.setattr(stack, "up", lambda: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda: None)
    monkeypatch.setattr(BenchmarkSandboxRunner, "build", lambda self: made.append(self))
    monkeypatch.setattr(BenchmarkSandboxRunner, "run", lambda self: None)
    return made


def test_a_run_uses_the_docker_backend_and_builds_unless_told_otherwise(
    task: LocalTask, tmp_path: Path, runners: list[BenchmarkSandboxRunner]
) -> None:
    assert cli.cmd_run(run_args(tmp_path / "pilot")) == 0

    [runner] = runners
    assert isinstance(runner.backend, DockerBackend) and not runner.prebuilt


@pytest.mark.parametrize("how", ["flag", "env"])
def test_prebuilt_is_a_flag_or_a_setting(
    how: str,
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if how == "env":
        monkeypatch.setenv("SSEBENCH_PREBUILT", "1")

    assert cli.cmd_run(run_args(tmp_path / "pilot", prebuilt=how == "flag")) == 0

    [runner] = runners
    assert runner.prebuilt


@pytest.mark.parametrize("extra", [{"tool_layer": "sandbox"}, {"plugin": ["a"]}, {"build": True}])
def test_prebuilt_excludes_what_changes_the_images(
    extra: dict[str, object],
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert cli.cmd_run(run_args(tmp_path / "pilot", prebuilt=True, **extra)) == 1
    assert "--prebuilt" in caplog.text and not runners


def test_the_backend_is_selected_by_flag_or_setting(
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SSEBENCH_BACKEND", "nope")

    assert cli.cmd_run(run_args(tmp_path / "pilot")) == 1
    assert "Unknown backend 'nope'" in caplog.text
    assert cli.cmd_run(run_args(tmp_path / "pilot", backend="docker")) == 0


def test_run_rejects_an_unknown_backend(caplog: pytest.LogCaptureFixture) -> None:
    argv = ["run", "--model", "m", "--agent", "dummy", "--task", "t", "--local", "datasets", "--backend", "nope"]
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)

    assert exit_info.value.code == 1
    assert "Unknown backend 'nope'" in caplog.text
