"""`ssebench build-case` rebuilds a case image whose task folder changed since it was built."""

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ssebench.cli import cli
from ssebench.tasks import LocalTask
from ssebench.tasks.local import FILES_LABEL, docker_build_case
from ssebench.tasks.manifest import task_files_digest

TASK = "demo-1"
NO_VALUE = "<no value>"


class Docker:
    """A Docker daemon with at most one case image, which carries `label`."""

    def __init__(self, image: str | None = None, label: str | None = None) -> None:
        self.image = image
        self.label = label
        self.builds: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["docker", "images", "-q"]:
            return subprocess.CompletedProcess(cmd, 0, "abc123\n" if cmd[-1] == self.image else "", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            if cmd[-1] != self.image:
                return subprocess.CompletedProcess(cmd, 1, "", "No such image")
            return subprocess.CompletedProcess(cmd, 0, f"{self.label or NO_VALUE}\n", "")
        if cmd[:3] == ["docker", "buildx", "build"]:
            self.builds.append(cmd)
            label = next(arg for arg in cmd if arg.startswith(f"{FILES_LABEL}="))
            self.image, self.label = cmd[cmd.index("-t") + 1], label.removeprefix(f"{FILES_LABEL}=")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected command {cmd}")


@pytest.fixture
def dataset(tmp_path: Path, make_task: Callable[..., Path]) -> Path:
    directory = tmp_path / "pilot"
    _ = make_task(directory, TASK)
    return directory


@pytest.fixture
def task(dataset: Path) -> LocalTask:
    return LocalTask(TASK, dataset)


def install(monkeypatch: pytest.MonkeyPatch, docker: Docker) -> None:
    monkeypatch.setattr(subprocess, "run", docker)


def run_build_case(dataset: Path, *extra: str) -> int:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["build-case", "--benchmarks", str(dataset), "--tasks", TASK, *extra])
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


# ==================== the digest ====================


def test_the_digest_follows_the_content_of_every_file(task: LocalTask) -> None:
    before = task_files_digest(task.task_path)

    assert task_files_digest(task.task_path) == before
    _ = (task.task_path / "sse" / "test.sh").write_text("#!/bin/sh\nmake check\n")
    changed = task_files_digest(task.task_path)
    assert changed != before
    _ = (task.task_path / "sse" / "extra.txt").write_text("new\n")
    assert task_files_digest(task.task_path) not in (before, changed)


def test_the_digest_follows_the_names_of_the_files(task: LocalTask) -> None:
    before = task_files_digest(task.task_path)

    _ = (task.task_path / "sse" / "test.sh").rename(task.task_path / "sse" / "check.sh")

    assert task_files_digest(task.task_path) != before


def test_the_case_image_is_built_with_the_digest_as_a_label(task: LocalTask, monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker()
    install(monkeypatch, docker)

    docker_build_case(task.task_path, task.docker_image_name)

    [build] = docker.builds
    assert f"{FILES_LABEL}={task_files_digest(task.task_path)}" in build


# ==================== build-case ====================


def test_a_missing_image_is_built(
    dataset: Path, task: LocalTask, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    docker = Docker()
    install(monkeypatch, docker)

    assert run_build_case(dataset) == 0

    assert len(docker.builds) == 1
    assert docker.image == task.docker_image_name


def test_an_up_to_date_image_is_skipped(
    dataset: Path, task: LocalTask, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    docker = Docker(task.docker_image_name, task_files_digest(task.task_path))
    install(monkeypatch, docker)
    caplog.set_level(logging.INFO)

    assert run_build_case(dataset) == 0

    assert docker.builds == []
    assert f"Skipping {TASK} - case image is up to date (use --force to rebuild)" in caplog.messages


def test_an_image_of_changed_files_is_rebuilt(
    dataset: Path, task: LocalTask, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    docker = Docker(task.docker_image_name, task_files_digest(task.task_path))
    install(monkeypatch, docker)
    _ = (task.task_path / "sse" / "diffs" / "patch.diff").write_text("a different fix\n")

    assert run_build_case(dataset) == 0

    assert len(docker.builds) == 1
    assert docker.label == task_files_digest(task.task_path)
    assert f"Rebuilding {TASK} - its files changed since the case image was built" in caplog.messages
    # The rebuilt image is current, so the next run skips it.
    assert run_build_case(dataset) == 0
    assert len(docker.builds) == 1


def test_an_image_without_a_record_of_its_files_is_skipped_with_a_warning(
    dataset: Path, task: LocalTask, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    docker = Docker(task.docker_image_name, None)
    install(monkeypatch, docker)

    assert run_build_case(dataset) == 0

    assert docker.builds == []
    [warning] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.getMessage() == (
        f"Skipping {TASK} - case image exists but records no task files, so it may be stale (use --force to rebuild)"
    )


@pytest.mark.parametrize("label", [None, "stale", "current"])
def test_force_rebuilds_every_image(
    label: str | None, dataset: Path, task: LocalTask, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = Docker(task.docker_image_name, task_files_digest(task.task_path) if label == "current" else label)
    install(monkeypatch, docker)

    assert run_build_case(dataset, "--force") == 0

    assert len(docker.builds) == 1
    assert docker.label == task_files_digest(task.task_path)


def test_a_failed_build_is_reported_and_fails_the_command(
    dataset: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def failing_build(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["docker", "buildx", "build"]:
            raise subprocess.CalledProcessError(1, cmd)
        return Docker()(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", failing_build)

    assert run_build_case(dataset) == 1

    assert any(f"Failed to build case image for {TASK}" in m for m in caplog.messages)
    assert f"  - {TASK}" in caplog.messages
