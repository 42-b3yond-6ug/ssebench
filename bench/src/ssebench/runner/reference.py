"""Reference runs: the `reference` agent applies the task's known fix instead of a model's patch.

A reference run checks a task and the grader, not a model, and makes no model calls. The runner
gives the fix to that agent alone, as a read-only file at `REFERENCE_PATCH_PATH`; the daemon still
withholds it during the agent phase, as for every agent. Results record `config.reference_run`,
and the container carries `REFERENCE_RUN_LABEL`, so a reference grade is never read as a model's.
"""

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from ssebench.arch import platform_args
from ssebench.tasks import Task

REFERENCE_AGENT = "reference"
REFERENCE_PATCH_PATH = "/reference/patch.diff"
REFERENCE_RUN_LABEL = "ssebench.reference-run"

# Paths in a task config are relative to this directory of the case image.
TASK_FILES_DIR = PurePosixPath("/ssebench")


def is_reference_run(agent_name: str) -> bool:
    return agent_name == REFERENCE_AGENT


def reference_patch_path(task: Task) -> PurePosixPath:
    """Where the task's case image keeps the reference patch.

    Raises:
        ValueError: If the task has no reference patch.
    """
    patch = task.get_task_metadata().files.patch
    if patch is None:
        raise ValueError(f"Task {task.name} has no reference patch (files.patch), so the reference agent cannot run it")
    return TASK_FILES_DIR / patch


def reference_patch_mount(agent_name: str, host_patch: Path | None) -> list[str]:
    """The `docker run` arguments that give the reference agent the patch; none for any other agent."""
    if not is_reference_run(agent_name):
        return []
    if host_patch is None:
        raise ValueError("a reference run needs the reference patch")
    return ["--mount", f"type=bind,source={host_patch},target={REFERENCE_PATCH_PATH},readonly"]


def reference_run_labels(agent_name: str) -> list[str]:
    """The `docker run` arguments that mark a reference run's container for the web UI."""
    return ["--label", f"{REFERENCE_RUN_LABEL}=true"] if is_reference_run(agent_name) else []


def copy_from_image(image: str, path: PurePosixPath, dest: Path, platform: str | None = None) -> None:
    """Copy one file out of an image without starting a container.

    `platform` (`linux/<arch>`) is the platform the image was built for; None takes the Docker host's own.

    Raises:
        RuntimeError: If Docker cannot create the container or copy the file.
    """
    create = subprocess.run(
        ["docker", "create", *platform_args(platform), image, "true"], capture_output=True, text=True
    )
    if create.returncode != 0:
        raise RuntimeError(f"Could not create a container from {image}: {create.stderr.strip()}")
    container = create.stdout.strip()
    try:
        copy = subprocess.run(
            ["docker", "cp", "--follow-link", f"{container}:{path}", str(dest)], capture_output=True, text=True
        )
        if copy.returncode != 0:
            raise RuntimeError(f"Could not copy {path} from {image}: {copy.stderr.strip()}")
    finally:
        _ = subprocess.run(["docker", "rm", container], capture_output=True)


@contextmanager
def reference_patch(agent_name: str, task: Task) -> Iterator[Path | None]:
    """The task's reference patch as a host file for the reference agent, or None for any other agent.

    The patch comes from the case image, which local and catalog tasks both have, so it is the
    file the daemon serves as the reference patch. It lives in a private temporary directory until
    the run ends.
    """
    if not is_reference_run(agent_name):
        yield None
        return
    source = reference_patch_path(task)
    with tempfile.TemporaryDirectory(prefix="ssebench-reference-") as tmp:
        host_patch = Path(tmp) / "patch.diff"
        copy_from_image(task.docker_image_name, source, host_patch, task.platform)
        # The agent reads it as the unprivileged model user.
        host_patch.chmod(0o644)
        yield host_patch
