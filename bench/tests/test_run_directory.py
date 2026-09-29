"""The run directory: the grade and the logs root-only in the container, the agent's files apart, and the
reference patch added from the task folder once the run is over."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from ssebench.agents import Agent
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
from ssebench.runner.result import RunConfig
from ssebench.runner.runner import (
    ARCHIVE_PATH,
    RESULTS_LABEL,
    RESULTS_PATH,
    prepare_run_directory,
    record_results,
    save_reference_patch,
)
from ssebench.tasks import LocalTask

TASK = "demo-1"


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def options(cmd: list[str], flag: str) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == flag]


def test_the_run_directory_starts_empty_with_an_archive(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "archive").mkdir(parents=True)
    _ = (run_dir / "archive" / "dialog.jsonl").write_text("{}\n")
    _ = (run_dir / "old.log").write_text("x")

    result = prepare_run_directory(run_dir)

    assert result == run_dir / "result.json"
    assert sorted(p.name for p in run_dir.iterdir()) == ["archive", "result.json"]
    assert not list((run_dir / "archive").iterdir())


def test_the_sandbox_container_gets_the_results_root_only_and_the_archive_apart(
    task: LocalTask, tmp_path: Path
) -> None:
    runner = BenchmarkSandboxRunner(NoModel(), Agent("dummy", task_name=TASK), task, 60, 2)
    runner.sandbox_image = "registry.test/image"
    run_dir = tmp_path / "run"

    cmd = runner.docker_command(run_dir)

    assert options(cmd, "-v") == [f"{run_dir}:{RESULTS_PATH}", f"{run_dir / 'archive'}:{ARCHIVE_PATH}"]
    assert f"{RESULTS_LABEL}={run_dir}" in options(cmd, "--label")
    assert not [arg for arg in cmd if "/sse_result" in arg]


def test_the_reference_patch_is_saved_from_the_task_folder(task: LocalTask, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    save_reference_patch(task, run_dir)
    assert (run_dir / "reference.patch").read_text() == "fix\n"


def test_a_task_without_a_folder_saves_no_reference_patch(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task, "task_folder", lambda: None)
    save_reference_patch(task, tmp_path)
    assert not (tmp_path / "reference.patch").exists()


def test_the_result_is_replaced_not_rewritten(task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # In the container, root writes result.json: the host user cannot write to it, only replace it.
    monkeypatch.chdir(tmp_path)
    result = tmp_path / "result.json"
    _ = result.write_text(
        '{"patch_result": {"build_success": true}, '
        '"runtime_result": {"agent_duration": 1, "agent_timeout": false, "evaluator_timeout": false}}'
    )
    result.chmod(0o444)
    config = RunConfig(agent="dummy", model="none", mode="sandbox", timeout=60, difficulty=2)

    record_results(task, config, 0.0, result)

    assert '"agent":"dummy"' in result.read_text()


def test_both_sidecar_containers_mount_the_results(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.chdir(tmp_path)
    runner = BenchmarkSidecarRunner(NoModel(), Agent("dummy", task_name=TASK), task, 60, 2)
    runner.sidecar_agentrt_image = "registry.test/agent"
    runner.sidecar_environ_image = "registry.test/environment"

    runner.run()

    runs = [cmd for cmd in commands if cmd[:2] == ["docker", "run"]]
    assert len(runs) == 2
    run_dir = tmp_path / "results" / TASK / "none" / "dummy"
    for cmd in runs:
        assert f"{run_dir}:{RESULTS_PATH}" in options(cmd, "-v")
        assert f"{run_dir / 'archive'}:{ARCHIVE_PATH}" in options(cmd, "-v")
    assert (run_dir / "reference.patch").read_text() == "fix\n"
