"""The architecture a run builds and runs for, and that every docker command of the run follows it."""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from ssebench import arch
from ssebench.agents import Agent
from ssebench.arch import Arch
from ssebench.dataset.generate import build_manifest, render_manifest
from ssebench.middleware import ToolLayer
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner, SidecarPair
from ssebench.runner import runner as runner_module
from ssebench.tasks import CatalogTask, LocalTask, load_catalog

TASK = "demo-1"
PILOT_TASK = "gjson-196-bf4efcb"


def host(monkeypatch: pytest.MonkeyPatch, machine: str) -> None:
    monkeypatch.setattr(arch.platform, "machine", lambda: machine)


def flag_values(cmd: list[str], flag: str) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == flag]


class Docker:
    """Records docker commands instead of running them."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.commands: list[list[str]] = []
        monkeypatch.setattr(subprocess, "run", self)

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def only(self) -> list[str]:
        [cmd] = self.commands
        return cmd


def dataset_with(make_task: Callable[..., Path], tmp_path: Path, arches: list[Arch] | None) -> Path:
    """A dataset with one task; a manifest lists `arches` for it, unless `arches` is None."""
    dataset = tmp_path / "demo"
    _ = make_task(dataset, TASK)
    if arches is not None:
        manifest = json.loads(render_manifest(build_manifest(dataset)))
        manifest["tasks"][0]["arch"] = arches
        _ = (dataset / "manifest.json").write_text(json.dumps(manifest))
    return dataset


@pytest.mark.parametrize(
    ("machine", "expected"),
    [("x86_64", "amd64"), ("AMD64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64"), ("riscv64", None), ("", None)],
)
def test_the_host_architecture_is_named_as_docker_names_it(
    monkeypatch: pytest.MonkeyPatch, machine: str, expected: Arch | None
) -> None:
    host(monkeypatch, machine)

    assert arch.host_arch() == expected


@pytest.mark.parametrize(
    ("machine", "supported", "chosen"),
    [
        ("x86_64", ["amd64"], "amd64"),
        ("aarch64", ["amd64"], "amd64"),
        ("aarch64", ["amd64", "arm64"], "arm64"),
        ("x86_64", ["arm64", "amd64"], "amd64"),
        ("riscv64", ["arm64", "amd64"], "arm64"),
    ],
)
def test_a_task_runs_on_the_host_architecture_when_it_supports_it(
    monkeypatch: pytest.MonkeyPatch, machine: str, supported: list[Arch], chosen: Arch
) -> None:
    host(monkeypatch, machine)

    assert arch.run_arch(supported) == chosen


def test_only_the_other_architecture_is_emulated(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch, "aarch64")
    assert (arch.is_emulated("amd64"), arch.is_emulated("arm64")) == (True, False)

    host(monkeypatch, "x86_64")
    assert (arch.is_emulated("amd64"), arch.is_emulated("arm64")) == (False, True)


def test_the_platform_option_is_left_out_without_a_platform() -> None:
    assert arch.platform_args("linux/amd64") == ["--platform", "linux/amd64"]
    assert arch.platform_args(None) == []


def test_the_warning_names_the_host_and_the_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch, "aarch64")

    warning = arch.emulation_warning("amd64")
    assert "aarch64" in warning
    assert "linux/amd64" in warning
    assert "slow" in warning
    assert "AddressSanitizer" in warning


def test_the_pilot_manifest_limits_its_tasks_to_amd64(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch, "aarch64")
    task = LocalTask(PILOT_TASK, Path(__file__).resolve().parents[2] / "datasets" / "pilot")

    assert task.supported_arches() == ["amd64"]
    assert task.platform == "linux/amd64"
    assert arch.is_emulated(task.arch)


@pytest.mark.parametrize(
    ("machine", "arches", "platform"),
    [
        ("aarch64", ["amd64"], "linux/amd64"),
        ("aarch64", ["amd64", "arm64"], "linux/arm64"),
        ("x86_64", ["amd64", "arm64"], "linux/amd64"),
        # Without a manifest a task follows the host.
        ("aarch64", None, "linux/arm64"),
        ("x86_64", None, "linux/amd64"),
    ],
)
def test_a_local_task_follows_the_manifest_of_its_dataset(
    monkeypatch: pytest.MonkeyPatch,
    make_task: Callable[..., Path],
    tmp_path: Path,
    machine: str,
    arches: list[Arch] | None,
    platform: str,
) -> None:
    host(monkeypatch, machine)

    assert LocalTask(TASK, dataset_with(make_task, tmp_path, arches)).platform == platform


def test_an_unreadable_manifest_does_not_limit_the_task(
    monkeypatch: pytest.MonkeyPatch,
    make_task: Callable[..., Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    host(monkeypatch, "aarch64")
    dataset = dataset_with(make_task, tmp_path, None)
    _ = (dataset / "manifest.json").write_text("{")

    assert LocalTask(TASK, dataset).platform == "linux/arm64"
    assert "Cannot read" in caplog.text


def test_the_case_image_is_built_for_the_run_platform(
    monkeypatch: pytest.MonkeyPatch, make_task: Callable[..., Path], tmp_path: Path
) -> None:
    host(monkeypatch, "aarch64")
    docker = Docker(monkeypatch)
    task = LocalTask(TASK, dataset_with(make_task, tmp_path, ["amd64"]))

    _ = task.docker_image(None)

    assert flag_values(docker.only(), "--platform") == ["linux/amd64"]


def test_the_case_image_is_pulled_for_the_run_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    host(monkeypatch, "aarch64")
    docker = Docker(monkeypatch)
    task = CatalogTask(load_catalog(), PILOT_TASK)

    _ = task.docker_image(None)

    assert docker.only() == ["docker", "pull", "--platform", "linux/amd64", task.docker_image_name]


def test_every_image_and_container_of_a_sandbox_run_uses_the_platform(
    monkeypatch: pytest.MonkeyPatch, make_task: Callable[..., Path], tmp_path: Path
) -> None:
    host(monkeypatch, "aarch64")
    task = LocalTask(TASK, dataset_with(make_task, tmp_path, ["amd64"]))
    pipelines: list[list[object]] = []
    monkeypatch.setattr(runner_module, "build_pipe", lambda pipeline: pipelines.append(list(pipeline)) or "image")
    agent = Agent("dummy", task_name=TASK, platform=task.platform)
    runner = BenchmarkSandboxRunner(NoModel(), agent, task, 60, 2)

    runner.build()

    [[_, layer, built_agent]] = pipelines
    assert cast(ToolLayer, layer).context.platform == "linux/amd64"
    assert cast(Agent, built_agent).platform == "linux/amd64"
    runner.sandbox_image = "registry.test/image"
    assert flag_values(runner.docker_command(tmp_path), "--platform") == ["linux/amd64"]


def test_every_image_and_container_of_a_sidecar_run_uses_the_platform(
    monkeypatch: pytest.MonkeyPatch, make_task: Callable[..., Path], tmp_path: Path
) -> None:
    host(monkeypatch, "aarch64")
    task = LocalTask(TASK, dataset_with(make_task, tmp_path, ["amd64"]))
    pipelines: list[list[object]] = []
    monkeypatch.setattr(runner_module, "build_pipe", lambda pipeline: pipelines.append(list(pipeline)) or "image")
    runner = BenchmarkSidecarRunner(NoModel(), Agent("dummy", task_name="sidecar", platform=task.platform), task, 60, 2)

    runner.build()

    [[agent_runtime, _], [_, environment]] = pipelines
    assert cast(ToolLayer, agent_runtime).context.platform == "linux/amd64"
    assert cast(ToolLayer, environment).context.platform == "linux/amd64"
    pair = SidecarPair(
        task_name=TASK,
        source_dir="/src/demo",
        results="r",
        archive="a",
        network="n",
        difficulty=2,
        platform=task.platform,
    )
    for options in (pair.environment_options(), pair.agent_options()):
        assert flag_values(options, "--platform") == ["linux/amd64"]


def test_the_run_platform_is_left_to_docker_when_none_is_given(tmp_path: Path) -> None:
    pair = SidecarPair(task_name=TASK, source_dir="/src/demo", results="r", archive="a", network="n", difficulty=2)

    assert "--platform" not in pair.environment_options()
    assert "--platform" not in pair.agent_options()


def test_an_agent_is_built_for_the_platform_of_its_base(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker(monkeypatch)

    _ = Agent("dummy", task_name=TASK, platform="linux/arm64").docker_image("base:1")
    _ = Agent("dummy", task_name=TASK).docker_image("base:1")

    with_platform, without = docker.commands
    assert flag_values(with_platform, "--platform") == ["linux/arm64"]
    assert "--platform" not in without
