"""`ssebench run --run-id`, and what a run does when the CLI is asked to stop."""

import argparse
import json
import os
import signal
import stat
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from ssebench import stack
from ssebench.agents import Agent
from ssebench.cli import cli
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
from ssebench.runner.lifecycle import RUN_ID_LABEL, RunGuard, check_run_id, run_container, run_id_labels
from ssebench.tasks import LocalTask

TASK = "demo-1"


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def sandbox_runner(task: LocalTask, run_id: str | None = None) -> BenchmarkSandboxRunner:
    runner = BenchmarkSandboxRunner(NoModel(), Agent("dummy", task_name=task.name), task, 60, 2, run_id=run_id)
    runner.sandbox_image = "registry.test/agent-image"
    return runner


def labels(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--label"]


@pytest.mark.parametrize("run_id", ["a", "3f2c9d1e-7b3a-4c1e-9a55-0d3e6b7c1a22", "run_1.beta-2", "A" * 64])
def test_run_ids_that_label_values_accept(run_id: str) -> None:
    assert check_run_id(run_id) == run_id


@pytest.mark.parametrize("run_id", ["", "-x", ".x", "a b", "a=b", "a,b", "a/b", "$(id)", "a\nb", "A" * 65, "é"])
def test_other_run_ids_are_rejected(run_id: str) -> None:
    with pytest.raises(ValueError):
        _ = check_run_id(run_id)
    with pytest.raises(SystemExit) as exit_info:
        _ = cli.build_parser()[0].parse_args(["run", "--agent", "dummy", "--task", TASK, "--run-id", run_id])
    assert exit_info.value.code == 2


def test_the_sandbox_container_carries_the_run_id(task: LocalTask, tmp_path: Path) -> None:
    assert f"{RUN_ID_LABEL}=abc-1" in labels(sandbox_runner(task, "abc-1").docker_command(tmp_path))
    assert not [label for label in labels(sandbox_runner(task).docker_command(tmp_path)) if RUN_ID_LABEL in label]
    assert run_id_labels(None) == [] and run_id_labels("x") == ["--label", f"{RUN_ID_LABEL}=x"]


def test_the_sidecar_task_container_carries_the_run_id(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.chdir(tmp_path)
    runner = BenchmarkSidecarRunner(NoModel(), Agent("dummy", task_name=task.name), task, 60, 2, run_id="side-1")
    runner.sidecar_agentrt_image, runner.sidecar_environ_image = "registry.test/agent", "registry.test/env"

    runner.run()

    [environment] = [cmd for cmd in commands if cmd[:3] == ["docker", "run", "--detach"]]
    assert f"{RUN_ID_LABEL}=side-1" in labels(environment)


def run_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "model": None,
        "agent": "reference",
        "task": TASK,
        "local": "",
        "catalog": "",
        "mode": "sandbox",
        "tool_layer": None,
        "timeout": 60,
        "difficulty": 2,
        "keep_container": False,
        "egress": "restricted",
        "run_id": None,
    }
    return argparse.Namespace(**(defaults | overrides))


def test_run_passes_the_run_id_to_the_runner(task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runners: list[BenchmarkSandboxRunner] = []
    monkeypatch.setattr(stack, "up", lambda: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda: None)
    monkeypatch.setattr(BenchmarkSandboxRunner, "build", lambda self: runners.append(self))
    monkeypatch.setattr(BenchmarkSandboxRunner, "run", lambda self: None)

    assert cli.cmd_run(run_args(local=str(tmp_path / "pilot"), run_id="from-the-ui")) == 0

    [runner] = runners
    assert runner.run_id == "from-the-ui"


# A stand-in for `docker` that runs a "container" until it is stopped: `run` writes the --cidfile and
# waits, `stop` ends the waiting `run` the way a real stop makes the entrypoint exit with 1.
FAKE_DOCKER = """#!/bin/sh
echo "$@" >> "$FAKE_DOCKER_LOG"
case "$1" in
run)
    shift
    while [ $# -gt 0 ]; do
        if [ "$1" = --cidfile ]; then echo container-1 > "$2"; fi
        shift
    done
    echo $$ > "$FAKE_DOCKER_PID"
    trap 'exit 1' TERM
    while :; do sleep 0.05; done
    ;;
stop)
    kill -TERM "$(cat "$FAKE_DOCKER_PID")"
    ;;
esac
"""


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    _ = docker.write_text(FAKE_DOCKER)
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "docker.log"
    _ = log.write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.setenv("FAKE_DOCKER_PID", str(tmp_path / "docker.pid"))
    monkeypatch.chdir(tmp_path)
    return log


def signal_when_started(tmp_path: Path, signum: signal.Signals, times: int = 1) -> threading.Thread:
    """Send this process `signum` once the fake container is running."""

    def send() -> None:
        pid_file = tmp_path / "docker.pid"
        for _ in range(400):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            threading.Event().wait(0.025)
        for _ in range(times):
            os.kill(os.getpid(), signum)

    thread = threading.Thread(target=send)
    thread.start()
    return thread


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_a_signal_stops_the_container_and_the_summary_is_still_written(
    signum: signal.Signals, task: LocalTask, tmp_path: Path, fake_docker: Path
) -> None:
    runner = sandbox_runner(task)
    thread = signal_when_started(tmp_path, signum)

    with RunGuard():
        runner.run()
    thread.join()

    assert "stop --time 20 container-1" in fake_docker.read_text().splitlines()
    summary = json.loads((tmp_path / "results" / f"{TASK}-dummy-none.json").read_text())
    assert summary["config"]["agent"] == "dummy"
    assert summary["patch_result"]["error_msg"] == "No result: evaluator did not produce output"
    assert summary["spend"] == 0


def test_the_handlers_are_restored_when_the_guard_ends(fake_docker: Path) -> None:
    before = {sig: signal.getsignal(sig) for sig in RunGuard.SIGNALS}

    with RunGuard():
        assert signal.getsignal(signal.SIGTERM) != before[signal.SIGTERM]

    assert {sig: signal.getsignal(sig) for sig in RunGuard.SIGNALS} == before


def test_a_container_that_finishes_on_its_own_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake)
    with RunGuard():
        run_container(["docker", "run", "--rm", "image"])

    [cmd] = commands
    assert cmd[:2] == ["docker", "run"] and cmd[2] == "--cidfile" and cmd[4:] == ["--rm", "image"]


def test_a_signal_before_the_container_exists_starts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no container may start"))

    with RunGuard() as guard:
        os.kill(os.getpid(), signal.SIGTERM)
        with pytest.raises(subprocess.CalledProcessError):
            run_container(["docker", "run", "image"])

    assert guard.signalled


def test_without_a_guard_the_container_runs_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        assert kwargs == {"check": True}
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake)
    run_container(["docker", "run", "image"])

    assert commands == [["docker", "run", "image"]]
