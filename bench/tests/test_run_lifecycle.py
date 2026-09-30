"""`ssebench run --run-id`, and what a run does when the CLI is asked to stop."""

import argparse
import json
import os
import re
import signal
import stat
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from ssebench import stack
from ssebench.agents import Agent
from ssebench.backends import RUN_ID_LABEL, DockerBackend, Images
from ssebench.cli import cli
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
from ssebench.runner.lifecycle import RunGuard, check_run_id, execute
from ssebench.tasks import LocalTask

from .conftest import FakeDocker

TASK = "demo-1"


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def sandbox_runner(task: LocalTask, run_id: str | None = None) -> BenchmarkSandboxRunner:
    runner = BenchmarkSandboxRunner(NoModel(), Agent("dummy", task_name=task.name), task, 60, 2, run_id=run_id)
    runner.images = Images(agent="registry.test/agent-image")
    return runner


def command(runner: BenchmarkSandboxRunner, results: Path) -> list[str]:
    return DockerBackend().run_command(runner.run_spec(results, None))


def labels(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--label"]


@pytest.mark.parametrize("run_id", ["a", "3f2c9d1e-7b3a-4c1e-9a55-0d3e6b7c1a22", "run_1.beta-2", "A" * 64])
def test_run_ids_that_label_values_accept(run_id: str) -> None:
    assert check_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id", ["", "-x", ".x", "a b", "a=b", "a,b", "a/b", "$(id)", "a\nb", "A" * 65, "é", "latest", "Latest", "LATEST"]
)
def test_other_run_ids_are_rejected(run_id: str) -> None:
    with pytest.raises(ValueError):
        _ = check_run_id(run_id)
    with pytest.raises(SystemExit) as exit_info:
        _ = cli.build_parser()[0].parse_args(["run", "--agent", "dummy", "--task", TASK, "--run-id", run_id])
    assert exit_info.value.code == 2


def test_the_sandbox_container_carries_the_run_id(task: LocalTask, tmp_path: Path) -> None:
    assert f"{RUN_ID_LABEL}=abc-1" in labels(command(sandbox_runner(task, "abc-1"), tmp_path))


def test_a_run_without_an_id_gets_a_generated_one(task: LocalTask, tmp_path: Path) -> None:
    first, second = sandbox_runner(task), sandbox_runner(task)

    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", first.run_id)
    assert first.run_id != second.run_id
    assert f"{RUN_ID_LABEL}={first.run_id}" in labels(command(first, tmp_path))


def test_the_sidecar_task_container_carries_the_run_id(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker: FakeDocker
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = BenchmarkSidecarRunner(NoModel(), Agent("dummy", task_name=task.name), task, 60, 2, run_id="side-1")
    runner.images = Images(agent="registry.test/agent", environment="registry.test/env")

    runner.run()

    [environment] = [cmd for cmd in docker.commands if cmd[:3] == ["docker", "run", "--detach"]]
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


def test_run_makes_an_id_for_the_runner_when_none_is_given(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runners: list[BenchmarkSandboxRunner] = []
    monkeypatch.setattr(stack, "up", lambda: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda: None)
    monkeypatch.setattr(BenchmarkSandboxRunner, "build", lambda self: runners.append(self))
    monkeypatch.setattr(BenchmarkSandboxRunner, "run", lambda self: None)

    assert cli.cmd_run(run_args(local=str(tmp_path / "pilot"))) == 0

    [runner] = runners
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", runner.run_id)


def test_run_refuses_an_id_that_has_results_before_it_starts_anything(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    taken = tmp_path / "results" / TASK / "none" / "reference" / "again"
    taken.mkdir(parents=True)

    def fail() -> None:
        raise AssertionError("the proxy must not start")

    monkeypatch.setattr(stack, "up", fail)

    assert cli.cmd_run(run_args(local=str(tmp_path / "pilot"), run_id="again")) == 1
    assert "already has results" in caplog.text
    assert list(taken.iterdir()) == []


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
    runner = sandbox_runner(task, "stopped")
    thread = signal_when_started(tmp_path, signum)

    with RunGuard():
        runner.run()
    thread.join()

    assert "stop --time 20 container-1" in fake_docker.read_text().splitlines()
    summary = json.loads((tmp_path / "results" / TASK / "none" / "dummy" / "stopped" / "summary.json").read_text())
    assert summary["run_id"] == "stopped"
    assert summary["config"]["agent"] == "dummy"
    assert summary["patch_result"]["error_msg"] == "No result: evaluator did not produce output"
    assert summary["spend"] == 0


def test_the_handlers_are_restored_when_the_guard_ends(fake_docker: Path) -> None:
    before = {sig: signal.getsignal(sig) for sig in RunGuard.SIGNALS}

    with RunGuard():
        assert signal.getsignal(signal.SIGTERM) != before[signal.SIGTERM]

    assert {sig: signal.getsignal(sig) for sig in RunGuard.SIGNALS} == before


def sandbox_spec(task: LocalTask, tmp_path: Path):
    return sandbox_runner(task, "spec").run_spec(tmp_path, None)


def test_a_container_that_finishes_on_its_own_is_left_alone(
    task: LocalTask, tmp_path: Path, docker: FakeDocker
) -> None:
    with RunGuard():
        assert execute(DockerBackend(), sandbox_spec(task, tmp_path), tmp_path) == 0

    [cmd] = docker.runs()
    assert cmd[:2] == ["docker", "run"] and cmd[2] == "--cidfile" and cmd[4] == "--rm"
    assert not [c for c in docker.commands if c[:2] == ["docker", "stop"]]


def test_a_signal_before_the_container_exists_starts_nothing(
    task: LocalTask, tmp_path: Path, docker: FakeDocker
) -> None:
    with RunGuard() as guard:
        os.kill(os.getpid(), signal.SIGTERM)
        assert execute(DockerBackend(), sandbox_spec(task, tmp_path), tmp_path) == 128 + signal.SIGTERM

    assert guard.signalled
    assert docker.commands == []


def test_without_a_guard_the_container_runs_as_before(task: LocalTask, tmp_path: Path, docker: FakeDocker) -> None:
    assert execute(DockerBackend(), sandbox_spec(task, tmp_path), tmp_path) == 0

    [cmd] = docker.runs()
    assert cmd[:2] == ["docker", "run"]
