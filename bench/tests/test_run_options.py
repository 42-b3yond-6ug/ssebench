"""`ssebench run --backend`, `--prebuilt`, `--egress` and `--require-pass`, and the settings that stand for them."""

import argparse
from collections.abc import Callable
from pathlib import Path

import pytest

from ssebench import stack
from ssebench.backends import DockerBackend
from ssebench.cli import cli
from ssebench.runner import BenchmarkSandboxRunner, RunOutcome
from ssebench.runner.reference import REFERENCE_AGENT
from ssebench.runner.result import EvaluationResult, FrameworkResult, PerTaskEvaluationResult, RunConfig
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
        "egress": None,
    }
    return argparse.Namespace(**(defaults | overrides))


def outcome(task: LocalTask, directory: Path, patch_result: dict[str, object]) -> RunOutcome:
    """A finished run with that grade."""
    runtime = {"agent_duration": 0, "agent_timeout": False, "evaluator_timeout": False}
    config = RunConfig(agent="dummy", model="none", mode="sandbox", timeout=60, difficulty=2)
    result = EvaluationResult.model_validate({"patch_result": patch_result, "runtime_result": runtime})
    summary = PerTaskEvaluationResult.build(task.get_task_metadata(), config, FrameworkResult(spend=0), result)
    return RunOutcome(directory, summary)


@pytest.fixture
def grade(tmp_path: Path, task: LocalTask) -> dict[str, object]:
    """The grade that the fake run ends with; a test replaces its entries."""
    return {"build_success": True, "pov_passed": 1, "pov_total": 1, "func_test_success": True}


@pytest.fixture
def runners(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, task: LocalTask, grade: dict[str, object]
) -> list[BenchmarkSandboxRunner]:
    made: list[BenchmarkSandboxRunner] = []
    monkeypatch.setattr(stack, "up", lambda: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda: None)
    monkeypatch.setattr(BenchmarkSandboxRunner, "build", lambda self: made.append(self))
    monkeypatch.setattr(BenchmarkSandboxRunner, "run", lambda self: outcome(task, tmp_path / "run", grade))
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


@pytest.mark.parametrize(
    ("flag", "setting", "expected"),
    [(None, None, "restricted"), (None, "open", "open"), ("restricted", "open", "restricted"), ("open", None, "open")],
)
def test_egress_is_the_flag_else_the_setting_else_restricted(
    flag: str | None,
    setting: str | None,
    expected: str,
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if setting:
        monkeypatch.setenv("SSEBENCH_EGRESS", setting)

    assert cli.cmd_run(run_args(tmp_path / "pilot", egress=flag)) == 0

    [runner] = runners
    assert runner.egress == expected


def test_a_setting_that_is_not_an_egress_policy_fails_before_the_run(
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SSEBENCH_EGRESS", "everything")

    assert cli.cmd_run(run_args(tmp_path / "pilot")) == 1
    assert "SSEBENCH_EGRESS='everything'" in caplog.text and not runners


def test_a_run_prints_its_grade_and_directory(
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    grade: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    grade.update(pov_passed=0)

    assert cli.cmd_run(run_args(tmp_path / "pilot")) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "Result: build passed, PoC 0/1 passed, functional tests passed, intent tests not run",
        "Grade: failed",
        f"Run directory: {tmp_path / 'run'}",
    ]


def test_a_run_that_was_not_graded_says_why(
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    grade: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    grade.clear()
    grade.update(status="error", error_msg="Timeout (30s)")

    assert cli.cmd_run(run_args(tmp_path / "pilot")) == 0

    assert "Grade: error (Timeout (30s))" in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize(
    ("grade_update", "status"),
    [({}, 0), ({"pov_passed": 0}, 1), ({"status": "error", "error_msg": "No check ran"}, 1)],
)
def test_require_pass_makes_a_grade_that_is_not_passed_the_exit_status(
    task: LocalTask,
    tmp_path: Path,
    runners: list[BenchmarkSandboxRunner],
    grade: dict[str, object],
    grade_update: dict[str, object],
    status: int,
) -> None:
    grade.update(grade_update)

    assert cli.cmd_run(run_args(tmp_path / "pilot", require_pass=True)) == status
    assert cli.cmd_run(run_args(tmp_path / "pilot")) == 0
