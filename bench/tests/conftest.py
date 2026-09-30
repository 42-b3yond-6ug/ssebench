import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from ssebench.runner import RunOutcome
from ssebench.runner.result import PatchResult, PerTaskEvaluationResult

DOCKERFILE = """\
ARG SSEBENCH_REGISTRY=registry.test/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:1.0.0

RUN git clone https://example.org/demo.git /src/demo

COPY sse/config.yaml /ssebench/config.yaml
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports
"""

TASK_FILES = {
    "sse/build.sh": "#!/bin/sh\nmake\n",
    "sse/run.sh": '#!/bin/sh\n./demo "$1"\n',
    "sse/test.sh": "#!/bin/sh\nmake test\n",
    "sse/diffs/patch.diff": "fix\n",
    "sse/diffs/test.diff": "tests\n",
    "sse/pocs/poc.bin": "crash\n",
    "sse/reports/crash.txt": "ERROR: AddressSanitizer\n",
}


def finished_run(_runner: object) -> RunOutcome:
    """Stands in for `BenchmarkRunner.run` in a test of the command line: a run that passed."""
    patch = PatchResult(build_success=True, pov_passed=1, pov_total=1, func_test_success=True)
    return RunOutcome(Path("run"), PerTaskEvaluationResult.model_construct(patch_result=patch))


def _task_config(task_id: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "project": "demo",
        "repository": "https://example.org/demo",
        "language": "c",
        "source": "/src/demo",
        "task_description": {"crash_report": ["reports/crash.txt"]},
        "scripts": {"build": "scripts/build.sh", "run": "scripts/run.sh", "test": "scripts/test.sh"},
        "files": {"patch": "diffs/patch.diff", "future_test": "diffs/test.diff", "poc": ["pocs/poc.bin"]},
        "sanitizer": "address",
    }


@pytest.fixture
def task_config() -> Callable[[str], dict[str, Any]]:
    """The config of a valid task, as a dict."""
    return _task_config


@pytest.fixture
def make_task() -> Callable[..., Path]:
    """Write a valid task folder, and a dataset.yaml if there is none.

    `config` entries replace top-level config keys, and None drops one.
    """

    def make(dataset: Path, task_id: str, config: dict[str, Any] | None = None, dockerfile: str = DOCKERFILE) -> Path:
        if not (dataset / "dataset.yaml").exists():
            dataset.mkdir(parents=True, exist_ok=True)
            _ = (dataset / "dataset.yaml").write_text("version: demo-v1\n")
        task = dataset / task_id
        for name, content in TASK_FILES.items():
            (task / name).parent.mkdir(parents=True, exist_ok=True)
            _ = (task / name).write_text(content)
        data = _task_config(task_id) | (config or {})
        data = {k: v for k, v in data.items() if v is not None}
        _ = (task / "sse" / "config.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
        _ = (task / "Dockerfile").write_text(dockerfile)
        return task

    return make


class FakePopen:
    """A `docker run` in the foreground whose container has already finished with `status`."""

    def __init__(self, status: int) -> None:
        self.returncode: int | None = None
        self.status = status

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = self.status
        return self.status

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class FakeDocker:
    """Records the docker commands of a run instead of running them.

    `docker create` answers with a container ID and `docker cp` writes its destination, as the reference
    patch is copied out of an image. `on_run` stands in for the container: it gets the command of each
    foreground `docker run` and returns the container's exit status.
    """

    def __init__(self, on_run: Callable[[list[str]], int] | None = None) -> None:
        self.commands: list[list[str]] = []
        self.on_run = on_run or (lambda cmd: 0)
        self.failing: Callable[[list[str]], bool] = lambda cmd: False

    def run(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        if self.failing(cmd):
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(125, cmd, "", "boom")
            return subprocess.CompletedProcess(cmd, 125, "", "boom")
        if cmd[:2] == ["docker", "create"]:
            return subprocess.CompletedProcess(cmd, 0, "container-id\n", "")
        if cmd[:2] == ["docker", "cp"]:
            _ = Path(cmd[-1]).write_text("diff --git a/f b/f\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def popen(self, cmd: list[str], **kwargs: object) -> FakePopen:
        self.commands.append(cmd)
        return FakePopen(self.on_run(cmd))

    def runs(self) -> list[list[str]]:
        """Every `docker run`, detached or not."""
        return [cmd for cmd in self.commands if cmd[:2] == ["docker", "run"]]

    def mentioning(self, text: str) -> list[list[str]]:
        return [cmd for cmd in self.commands if any(text in arg for arg in cmd)]


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    """`docker` replaced by a recorder, for `subprocess.run` and `subprocess.Popen`."""
    fake = FakeDocker()
    monkeypatch.setattr(subprocess, "run", fake.run)
    monkeypatch.setattr(subprocess, "Popen", fake.popen)
    return fake
