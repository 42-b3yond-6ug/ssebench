import argparse
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from ssebench import paths, stack
from ssebench.agents import Agent
from ssebench.cli import cli
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRuner
from ssebench.runner.reference import (
    REFERENCE_AGENT,
    REFERENCE_PATCH_PATH,
    REFERENCE_RUN_LABEL,
    reference_patch_mount,
)
from ssebench.runner.result import RunConfig
from ssebench.runner.runner import record_results
from ssebench.tasks import LocalTask

AGENTS = sorted(p.parent.name for p in paths.agents_dir().glob("*/agent.yaml"))
OTHER_AGENTS = [name for name in AGENTS if name != REFERENCE_AGENT]
TASK = "demo-1"


class Docker:
    """Records docker commands instead of running them; `docker cp` writes the destination file."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        if cmd[:2] == ["docker", "create"]:
            return subprocess.CompletedProcess(cmd, 0, "container-id\n", "")
        if cmd[:2] == ["docker", "cp"]:
            _ = Path(cmd[-1]).write_text("diff --git a/f b/f\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def runs(self) -> list[list[str]]:
        return [cmd for cmd in self.commands if cmd[:2] == ["docker", "run"]]

    def mentioning(self, text: str) -> list[list[str]]:
        return [cmd for cmd in self.commands if any(text in arg for arg in cmd)]


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


@pytest.fixture
def docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Docker:
    fake = Docker()
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.chdir(tmp_path)
    return fake


def sandbox_runner(agent: str, task: LocalTask) -> BenchmarkSandboxRunner:
    runner = BenchmarkSandboxRunner(NoModel(), Agent(agent, task_name=task.name), task, 60, 2)
    runner.sandbox_image = "registry.test/agent-image"
    return runner


def sidecar_runner(agent: str, task: LocalTask) -> BenchmarkSidecarRuner:
    runner = BenchmarkSidecarRuner(NoModel(), Agent(agent, task_name=task.name), task, 60, 2)
    runner.sidecar_agentrt_image = "registry.test/agent-image"
    runner.sidecar_environ_image = "registry.test/environment-image"
    return runner


def mounts(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg in ("-v", "--mount")]


def test_the_agents_are_found() -> None:
    assert REFERENCE_AGENT in AGENTS
    assert "dummy" in OTHER_AGENTS


@pytest.mark.parametrize("agent", [*OTHER_AGENTS, "reference-like", "Reference"])
def test_no_other_agent_gets_the_patch_mount(agent: str) -> None:
    assert reference_patch_mount(agent, Path("/tmp/patch.diff")) == []


def test_the_reference_agent_gets_a_read_only_mount() -> None:
    assert reference_patch_mount(REFERENCE_AGENT, Path("/tmp/x/patch.diff")) == [
        "--mount",
        f"type=bind,source=/tmp/x/patch.diff,target={REFERENCE_PATCH_PATH},readonly",
    ]


@pytest.mark.parametrize("agent", OTHER_AGENTS)
def test_sandbox_command_withholds_a_patch_from_other_agents(agent: str, task: LocalTask, tmp_path: Path) -> None:
    cmd = sandbox_runner(agent, task).docker_command(tmp_path, Path("/tmp/patch.diff"))

    assert not [arg for arg in cmd if REFERENCE_PATCH_PATH in arg or "patch.diff" in arg or REFERENCE_RUN_LABEL in arg]


@pytest.mark.parametrize("make_runner", [sandbox_runner, sidecar_runner])
@pytest.mark.parametrize("agent", OTHER_AGENTS)
def test_other_agents_run_without_the_reference_patch(
    agent: str,
    make_runner: Callable[..., BenchmarkSandboxRunner | BenchmarkSidecarRuner],
    task: LocalTask,
    docker: Docker,
) -> None:
    make_runner(agent, task).run()

    assert docker.runs()
    assert not docker.mentioning(REFERENCE_PATCH_PATH)
    assert not docker.mentioning("patch.diff")
    assert not docker.mentioning(REFERENCE_RUN_LABEL)
    assert not [cmd for cmd in docker.commands if cmd[:2] in (["docker", "create"], ["docker", "cp"])]
    summary = json.loads((Path("results") / f"{TASK}-{agent}-none.json").read_text())
    assert summary["config"]["reference_run"] is False


@pytest.mark.parametrize("make_runner", [sandbox_runner, sidecar_runner])
def test_reference_run_mounts_the_patch_from_the_case_image(
    make_runner: Callable[..., BenchmarkSandboxRunner | BenchmarkSidecarRuner], task: LocalTask, docker: Docker
) -> None:
    make_runner(REFERENCE_AGENT, task).run()

    [copy] = [cmd for cmd in docker.commands if cmd[:2] == ["docker", "cp"]]
    assert copy[-2] == "container-id:/ssebench/diffs/patch.diff"
    [create] = [cmd for cmd in docker.commands if cmd[:2] == ["docker", "create"]]
    assert task.docker_image_name in create

    [agent_run] = [cmd for cmd in docker.runs() if "registry.test/agent-image" in cmd]
    [mount] = [m for m in mounts(agent_run) if REFERENCE_PATCH_PATH in m]
    assert mount.endswith(f"target={REFERENCE_PATCH_PATH},readonly")
    # The temporary copy is gone once the run ends.
    assert not Path(mount.split(",")[1].removeprefix("source=")).exists()

    labelled = docker.mentioning(f"{REFERENCE_RUN_LABEL}=true")
    assert len(labelled) == 1 and "ssebench.webui=true" in labelled[0]


@pytest.mark.parametrize("make_runner", [sandbox_runner, sidecar_runner])
def test_reference_run_results_are_labelled(
    make_runner: Callable[..., BenchmarkSandboxRunner | BenchmarkSidecarRuner], task: LocalTask, docker: Docker
) -> None:
    make_runner(REFERENCE_AGENT, task).run()

    results = Path("results")
    summary = json.loads((results / f"{TASK}-{REFERENCE_AGENT}-none.json").read_text())
    result = json.loads((results / TASK / "none" / REFERENCE_AGENT / "result.json").read_text())
    for record in (summary, result):
        assert record["config"]["agent"] == REFERENCE_AGENT
        assert record["config"]["model"] == "none"
        assert record["config"]["reference_run"] is True
    assert summary["spend"] == 0


def test_record_results_adds_the_config_to_result_json(task: LocalTask, tmp_path: Path, docker: Docker) -> None:
    grade = {
        "patch_result": {"build_success": True, "pov_passed": 1, "pov_total": 1, "func_test_success": True},
        "runtime_result": {"agent_duration": 3, "agent_timeout": False, "evaluator_timeout": False},
    }
    evaluator_file = tmp_path / "result.json"
    _ = evaluator_file.write_text(json.dumps(grade))
    config = RunConfig(agent="dummy", model="m", mode="sandbox", timeout=60, difficulty=2)

    record_results(task, config, 0.5, evaluator_file)

    result = json.loads(evaluator_file.read_text())
    assert result["patch_result"]["pov_passed"] == 1
    assert result["config"] == config.model_dump()
    summary = json.loads((tmp_path / "results" / f"{TASK}-dummy-m.json").read_text())
    assert summary["spend"] == 0.5


def run_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "model": None,
        "agent": REFERENCE_AGENT,
        "task": TASK,
        "local": "",
        "catalog": "",
        "mode": "sandbox",
        "tool_layer": None,
        "timeout": 60,
        "difficulty": 2,
        "keep_container": False,
        "egress": "restricted",
    }
    return argparse.Namespace(**(defaults | overrides))


def test_model_is_required_for_other_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack, "up", lambda: pytest.fail("the proxy must not start"))

    assert cli.cmd_run(run_args(agent="dummy", local="datasets/pilot")) == 1


@pytest.mark.parametrize("model", [None, "none", "some-model"])
def test_reference_run_needs_no_model(
    model: str | None, task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runners: list[BenchmarkSandboxRunner] = []
    monkeypatch.setattr(stack, "up", lambda: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda: None)
    monkeypatch.setattr(cli, "Model", lambda name: pytest.fail("no proxy key may be created"))
    monkeypatch.setattr(BenchmarkSandboxRunner, "build", lambda self: runners.append(self))
    monkeypatch.setattr(BenchmarkSandboxRunner, "run", lambda self: None)

    assert cli.cmd_run(run_args(model=model, local=str(tmp_path / "pilot"))) == 0

    [runner] = runners
    assert isinstance(runner.model, NoModel)
    assert runner.model.model_name == "none"


def test_reference_run_needs_a_reference_patch(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK, {"files": {"poc": ["pocs/poc.bin"]}})
    monkeypatch.setattr(stack, "up", lambda: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda: None)
    monkeypatch.setattr(BenchmarkSandboxRunner, "build", lambda self: pytest.fail("nothing may be built"))

    assert cli.cmd_run(run_args(local=str(dataset))) == 1
