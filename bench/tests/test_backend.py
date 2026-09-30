"""The runner talks to a Backend and to nothing else; the Docker backend implements it, and prebuilt runs skip builds."""

import io
import json
import logging
import os
import signal
import subprocess
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import override

import pytest

from ssebench.agents import Agent
from ssebench.backends import (
    RESULTS_LABEL,
    RUN_ID_LABEL,
    Backend,
    BackendError,
    DockerBackend,
    DockerRun,
    ImageRequest,
    Images,
    ImageUnavailableError,
    RunHandle,
    RunInfo,
    RunSpec,
    prebuilt_images,
)
from ssebench.backends import docker as docker_module
from ssebench.errors import UserError
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
from ssebench.runner.lifecycle import RunGuard
from ssebench.runner.reference import REFERENCE_AGENT
from ssebench.tasks import LocalTask

from .conftest import FakeDocker

TASK = "demo-1"
GRADE = {
    "patch_result": {"build_success": True, "pov_passed": 0, "pov_total": 1, "func_test_success": True},
    "runtime_result": {"agent_duration": 3, "agent_timeout": False, "evaluator_timeout": False},
}


class FakeBackend(Backend):
    """A backend with no container platform: it keeps a log of the calls and a "remote" copy of the results.

    Its containers do not share a file system with the runner, so the grade reaches the run directory
    only through `collect_results`.
    """

    name = "fake"

    def __init__(self, *, builds: bool = True, status: int = 0, start_error: str | None = None) -> None:
        self.builds_images = builds
        self.status = status
        self.start_error = start_error
        self.calls: list[str] = []
        self.requests: list[ImageRequest] = []
        self.specs: list[RunSpec] = []
        self.copied: list[str] = []
        self.remote_files = {"result.json": json.dumps(GRADE), "final.patch": "patch\n"}
        self.stopped = threading.Event()
        self.hold = False

    @override
    def prepare_images(self, request: ImageRequest) -> Images:
        self.calls.append("prepare_images")
        self.requests.append(request)
        if request.prebuilt:
            return prebuilt_images(request)
        return Images(agent="built/agent", environment="built/env" if request.mode == "sidecar" else None)

    @override
    def copy_from_image(self, image: str, path: PurePosixPath, dest: Path, platform: str | None = None) -> None:
        self.calls.append("copy_from_image")
        self.copied.append(image)
        _ = dest.write_text("diff --git a/f b/f\n")

    @override
    def start(self, spec: RunSpec) -> RunHandle:
        self.calls.append("start")
        self.specs.append(spec)
        if self.start_error:
            raise BackendError(self.start_error)
        return RunHandle(run_id=spec.run_id, name="fake-1", keep=spec.keep)

    @override
    def wait(self, handle: RunHandle, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if self.hold:
            assert self.stopped.wait(10), "the run was never stopped"
            return 143
        return self.status

    @override
    def logs(self, handle: RunHandle, *, follow: bool = False) -> Iterator[str]:
        yield "line\n"

    @override
    def collect_results(self, handle: RunHandle, dest: Path) -> None:
        self.calls.append("collect_results")
        for name, content in self.remote_files.items():
            (dest / name).unlink(missing_ok=True)
            _ = (dest / name).write_text(content)

    @override
    def stop(self, handle: RunHandle, grace: int = 20) -> None:
        self.calls.append("stop")
        self.stopped.set()

    @override
    def cleanup(self, handle: RunHandle) -> None:
        self.calls.append("cleanup")

    @override
    def list_runs(self, labels: Mapping[str, str] | None = None) -> list[RunInfo]:
        return []


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


@pytest.fixture(autouse=True)
def no_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"the runner ran a process: {args}")

    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)
    monkeypatch.chdir(tmp_path)


def sandbox(task: LocalTask, backend: Backend, agent: str = "dummy", **kwargs: object) -> BenchmarkSandboxRunner:
    return BenchmarkSandboxRunner(
        NoModel(),
        Agent(agent, task_name=task.name),
        task,
        60,
        2,
        run_id="r1",
        backend=backend,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def sidecar(task: LocalTask, backend: Backend, agent: str = "dummy", **kwargs: object) -> BenchmarkSidecarRunner:
    return BenchmarkSidecarRunner(
        NoModel(),
        Agent(agent, task_name="sidecar"),
        task,
        60,
        2,
        run_id="r1",
        backend=backend,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def run_dir(agent: str = "dummy") -> Path:
    return Path("results") / TASK / "none" / agent / "r1"


# ==================== the runner and the interface ====================


@pytest.mark.parametrize("make_runner", [sandbox, sidecar])
def test_a_run_goes_through_the_interface_in_order(task: LocalTask, make_runner: Callable[..., object]) -> None:
    backend = FakeBackend()
    runner = make_runner(task, backend)

    runner.build()  # pyright: ignore[reportAttributeAccessIssue]
    runner.run()  # pyright: ignore[reportAttributeAccessIssue]

    assert backend.calls == ["prepare_images", "start", "wait", "collect_results", "cleanup"]


@pytest.mark.parametrize("make_runner", [sandbox, sidecar])
def test_the_grade_reaches_the_run_directory_through_collect_results(
    task: LocalTask, make_runner: Callable[..., object]
) -> None:
    backend = FakeBackend()
    runner = make_runner(task, backend)
    runner.build()  # pyright: ignore[reportAttributeAccessIssue]

    runner.run()  # pyright: ignore[reportAttributeAccessIssue]

    summary = json.loads((run_dir() / "summary.json").read_text())
    assert summary["patch_result"]["build_success"] is True
    assert summary["run_id"] == "r1"
    assert (run_dir() / "final.patch").read_text() == "patch\n"
    assert json.loads((run_dir() / "result.json").read_text())["config"]["agent"] == "dummy"


def test_a_sandbox_spec_describes_the_whole_run(task: LocalTask) -> None:
    backend = FakeBackend()
    runner = sandbox(task, backend, keep_container=True, egress="open", plugins=["a"], select_plugins=True)
    runner.build()
    runner.run()

    [spec] = backend.specs
    results = run_dir().absolute()
    assert (spec.mode, spec.image, spec.sidecar) == ("sandbox", "built/agent", None)
    assert spec.results.source == str(results) and spec.results.target == "/var/lib/ssebench/results"
    assert spec.archive.source == str(results / "archive") and spec.archive.target == "/tmp/sse-archive"
    assert spec.network.egress == "open" and spec.keep and spec.timeout == 60
    assert spec.platform == task.platform
    assert spec.env["SSE_KEEP_ALIVE"] == "1" and spec.env["SSE_PLUGINS"] == "a" and spec.env["TIMEOUT"] == "60"
    assert spec.labels[RUN_ID_LABEL] == "r1" and spec.labels[RESULTS_LABEL] == str(results)
    assert spec.labels["ssebench.task-id"] == TASK and spec.labels["ssebench.agent"] == "dummy"
    assert spec.artifacts == ()
    assert "SSE_API_KEY" not in repr(spec)


def test_a_sidecar_spec_carries_the_pair(task: LocalTask) -> None:
    backend = FakeBackend()
    runner = sidecar(task, backend, keep_container=True)
    runner.build()
    runner.run()

    [spec] = backend.specs
    assert spec.mode == "sidecar" and spec.image == "built/agent"
    assert spec.sidecar is not None
    assert spec.sidecar.environment_image == "built/env"
    assert spec.sidecar.source_dir == "/src/demo" and spec.sidecar.difficulty == 2 and spec.sidecar.keep_alive
    assert set(spec.env) == {"SSE_API_KEY", "SSE_BASE_URL", "SSE_MODEL_NAME", "TIMEOUT"}


def test_the_reference_patch_is_a_read_only_artifact(task: LocalTask) -> None:
    backend = FakeBackend()
    runner = sandbox(task, backend, REFERENCE_AGENT)
    runner.build()
    runner.run()

    [spec] = backend.specs
    [artifact] = spec.artifacts
    assert artifact.target == "/reference/patch.diff" and artifact.read_only
    assert spec.labels["ssebench.reference-run"] == "true"
    assert backend.copied == [task.docker_image_name]


def test_a_run_that_cannot_start_still_records_its_summary(task: LocalTask, caplog: pytest.LogCaptureFixture) -> None:
    backend = FakeBackend(start_error="no capacity")
    runner = sidecar(task, backend)
    runner.build()

    runner.run()

    assert "Sidecar run failed: no capacity" in caplog.text
    assert backend.calls == ["prepare_images", "start"]
    assert (run_dir() / "summary.json").is_file()


def test_a_non_zero_exit_is_reported_without_the_command_line(
    task: LocalTask, caplog: pytest.LogCaptureFixture
) -> None:
    runner = sidecar(task, FakeBackend(status=3))
    runner.build()

    runner.run()

    assert "Sidecar run failed: `docker run` exited with status 3" in caplog.text


def test_the_backend_cleans_up_when_waiting_is_interrupted(task: LocalTask) -> None:
    class Interrupted(FakeBackend):
        @override
        def wait(self, handle: RunHandle, timeout: float | None = None) -> int:
            raise KeyboardInterrupt

    backend = Interrupted()
    runner = sandbox(task, backend)
    runner.build()

    with pytest.raises(KeyboardInterrupt):
        runner.run()

    assert backend.calls[-1] == "cleanup"


def test_a_signal_stops_the_run_through_the_backend_and_the_summary_is_written(task: LocalTask) -> None:
    backend = FakeBackend()
    backend.hold = True
    runner = sandbox(task, backend)
    runner.build()

    def send() -> None:
        while "wait" not in backend.calls:
            threading.Event().wait(0.01)
        os.kill(os.getpid(), signal.SIGTERM)

    thread = threading.Thread(target=send)
    thread.start()
    with RunGuard():
        runner.run()
    thread.join()

    assert backend.calls.count("stop") == 1
    assert (run_dir() / "summary.json").is_file()


# ==================== images ====================


def test_a_backend_that_cannot_build_needs_prebuilt_images(task: LocalTask) -> None:
    with pytest.raises(UserError, match="cannot build images"):
        sandbox(task, FakeBackend(builds=False)).build()

    backend = FakeBackend(builds=False)
    sandbox(task, backend, prebuilt=True).build()
    assert backend.requests[0].prebuilt


@pytest.mark.parametrize("extra", [{"tool_layer": "other"}, {"select_plugins": True, "plugins": ["p"]}])
def test_prebuilt_images_come_with_their_tool_layer_and_plugins(task: LocalTask, extra: dict[str, object]) -> None:
    with pytest.raises(UserError):
        _ = sandbox(task, FakeBackend(), prebuilt=True, **extra)  # pyright: ignore[reportArgumentType]


def test_prebuilt_sandbox_images_are_named_by_agent_and_task(task: LocalTask) -> None:
    agent = Agent("dummy", task_name=task.name)
    request = ImageRequest(mode="sandbox", task=task, agent=agent, prebuilt=True)

    images = prebuilt_images(request)

    assert images == Images(agent=agent.image_name)
    assert images.agent.endswith(f"/agent-dummy/{TASK}:{agent.agent_config.version}")


def test_prebuilt_sidecar_images_are_the_shared_agent_and_the_task_environment(task: LocalTask) -> None:
    agent = Agent("dummy", task_name="sidecar")
    images = prebuilt_images(ImageRequest(mode="sidecar", task=task, agent=agent, prebuilt=True))

    assert images.agent.endswith("/agent-dummy/sidecar:" + agent.agent_config.version)
    assert images.environment is not None and f"/tool-sidecar/{TASK}:" in images.environment


def test_a_prebuilt_reference_run_takes_the_patch_from_the_image_it_runs(task: LocalTask) -> None:
    backend = FakeBackend(builds=False)
    runner = sidecar(task, backend, REFERENCE_AGENT, prebuilt=True)
    runner.build()
    runner.run()

    assert backend.copied == [prebuilt_images(backend.requests[0]).environment]


# ==================== the Docker backend ====================


def test_prebuilt_images_are_pulled_for_the_platform_and_never_built(
    task: LocalTask, monkeypatch: pytest.MonkeyPatch, docker: FakeDocker
) -> None:
    monkeypatch.setattr(docker_module, "build_pipe", lambda pipeline: pytest.fail("nothing may be built"))
    runner = sidecar(task, DockerBackend(), prebuilt=True)

    runner.build()

    assert runner.images is not None and runner.images.environment is not None
    pulls = [cmd for cmd in docker.commands if cmd[:2] == ["docker", "pull"]]
    assert sorted(cmd[-1] for cmd in pulls) == sorted([runner.images.agent, runner.images.environment])
    assert all(cmd[2:4] == ["--platform", task.platform] for cmd in pulls)
    assert not [cmd for cmd in docker.commands if "buildx" in cmd]


def test_a_prebuilt_image_on_this_machine_is_used_when_the_pull_fails(
    task: LocalTask, docker: FakeDocker, caplog: pytest.LogCaptureFixture
) -> None:
    docker.failing = lambda cmd: cmd[:2] == ["docker", "pull"]

    with caplog.at_level(logging.WARNING):
        sandbox(task, DockerBackend(), prebuilt=True).build()

    assert "using the copy on this machine" in caplog.text


def test_a_prebuilt_image_that_is_nowhere_is_an_error(task: LocalTask, docker: FakeDocker) -> None:
    docker.failing = lambda cmd: cmd[:2] in (["docker", "pull"], ["docker", "image"])

    with pytest.raises(ImageUnavailableError, match="not in the registry or on this machine"):
        sandbox(task, DockerBackend(), prebuilt=True).build()


def test_a_sidecar_that_fails_to_start_leaves_nothing_behind(task: LocalTask, docker: FakeDocker) -> None:
    docker.failing = lambda cmd: cmd[:3] == ["docker", "run", "--detach"]
    runner = sidecar(task, DockerBackend())
    runner.images = Images(agent="registry.test/agent", environment="registry.test/env")

    with pytest.raises(BackendError, match=r"Starting the environment container .* failed: `docker run --detach`"):
        DockerBackend().start(runner.run_spec(Path("/results"), None))

    assert [cmd[:3] for cmd in docker.commands if cmd[:2] in (["docker", "rm"], ["docker", "volume"])] == [
        ["docker", "volume", "create"],
        ["docker", "volume", "create"],
        ["docker", "rm", "--force"],
        ["docker", "volume", "rm"],
    ]
    assert not [cmd for cmd in docker.commands if cmd[:2] == ["docker", "run"] and "--detach" not in cmd]


def test_a_start_error_never_shows_the_model_key(task: LocalTask, docker: FakeDocker) -> None:
    docker.failing = lambda cmd: cmd[:3] == ["docker", "run", "--detach"]
    runner = sidecar(task, DockerBackend())
    runner.images = Images(agent="registry.test/agent", environment="registry.test/env")
    spec = runner.run_spec(Path("/results"), None)
    secret = spec.env["SSE_API_KEY"] + "secret-value"
    spec = RunSpec(**{**spec.__dict__, "env": {**spec.env, "SSE_API_KEY": secret}})  # pyright: ignore[reportArgumentType]

    with pytest.raises(BackendError) as error:
        DockerBackend().start(spec)

    assert secret not in str(error.value)


def inspect_output(*entries: dict[str, object]) -> str:
    return json.dumps(list(entries))


def test_runs_are_listed_and_inspected_by_label(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    entry = {
        "Id": "abc",
        "Name": "/ssebench-env-demo-1-x",
        "Config": {"Image": "img", "Labels": {RUN_ID_LABEL: "r1", "ssebench.agent": "dummy"}},
        "State": {"Status": "exited", "ExitCode": 143},
    }

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        out = "abc\n" if cmd[:2] == ["docker", "ps"] else inspect_output(entry)
        return subprocess.CompletedProcess(cmd, 0, out, "")

    monkeypatch.setattr(subprocess, "run", fake)

    [info] = DockerBackend().list_runs({RUN_ID_LABEL: "r1"})
    found = DockerBackend().inspect_run("r1")

    assert commands[0][-2:] == ["--filter", f"label={RUN_ID_LABEL}=r1"]
    assert (info.run_id, info.name, info.state, info.exit_code) == ("r1", "ssebench-env-demo-1-x", "exited", 143)
    assert info.labels["ssebench.agent"] == "dummy"
    assert isinstance(info.handle, DockerRun) and info.handle.container == "abc"
    assert found is not None and found.run_id == "r1"


def test_no_runs_is_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))

    assert DockerBackend().list_runs() == []
    assert DockerBackend().inspect_run("nope") is None


def test_a_found_run_is_stopped_and_removed_by_container(docker: FakeDocker) -> None:
    handle = DockerRun(run_id="r1", container="abc")
    backend = DockerBackend()

    backend.stop(handle, 5)
    backend.cleanup(handle)

    assert docker.commands == [["docker", "stop", "--time", "5", "abc"], ["docker", "rm", "--force", "abc"]]


def test_a_kept_pair_is_left_in_place(task: LocalTask, docker: FakeDocker, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    runner = sidecar(task, DockerBackend(), keep_container=True)
    runner.images = Images(agent="registry.test/agent", environment="registry.test/env")

    runner.run()

    assert not [
        cmd for cmd in docker.commands if cmd[:2] in (["docker", "rm"], ["docker", "volume"]) and "create" not in cmd
    ]
    assert "Kept the containers and volumes labelled ssebench.run=" in caplog.text


class LogProcess:
    """A `docker logs` process that printed two lines and finished."""

    def __init__(self) -> None:
        self.stdout = io.StringIO("a\nb\n")
        self.returncode = 0

    def poll(self) -> int:
        return 0

    def wait(self) -> int:
        return 0


def test_logs_are_read_from_the_container(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def popen(cmd: list[str], **kwargs: object) -> LogProcess:
        seen.append(cmd)
        return LogProcess()

    monkeypatch.setattr(subprocess, "Popen", popen)

    lines = list(DockerBackend().logs(DockerRun(run_id="r1", container="abc"), follow=True))

    assert lines == ["a\n", "b\n"]
    assert seen == [["docker", "logs", "--follow", "abc"]]
