"""Reference runs: the `reference` agent applies the task's known fix instead of a model's patch.

A reference run checks a task and the grader, not a model, and makes no model calls. The runner
gives the fix to that agent alone, as a read-only file at `REFERENCE_PATCH_PATH`; the daemon still
withholds it during the agent phase, as for every agent. Results record `config.reference_run`,
and the container carries `REFERENCE_RUN_LABEL`, so a reference grade is never read as a model's.
"""

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from ssebench.backends import Backend, Mount
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


def reference_artifacts(agent_name: str, host_patch: Path | None) -> tuple[Mount, ...]:
    """The files that give the reference agent the patch, read-only; none for any other agent."""
    if not is_reference_run(agent_name):
        return ()
    if host_patch is None:
        raise ValueError("a reference run needs the reference patch")
    return (Mount(source=str(host_patch), target=REFERENCE_PATCH_PATH, read_only=True),)


def reference_run_labels(agent_name: str) -> dict[str, str]:
    """The labels that mark a reference run's container for the web UI."""
    return {REFERENCE_RUN_LABEL: "true"} if is_reference_run(agent_name) else {}


@contextmanager
def reference_patch(backend: Backend, agent_name: str, task: Task, image: str | None = None) -> Iterator[Path | None]:
    """The task's reference patch as a host file for the reference agent, or None for any other agent.

    The patch comes from `image`, the task's case image unless the run uses prebuilt images and has no case
    image, so it is the file the daemon serves as the reference patch. It lives in a private temporary
    directory until the run ends.
    """
    if not is_reference_run(agent_name):
        yield None
        return
    source = reference_patch_path(task)
    with tempfile.TemporaryDirectory(prefix="ssebench-reference-") as tmp:
        host_patch = Path(tmp) / "patch.diff"
        backend.copy_from_image(image or task.docker_image_name, source, host_patch, task.platform)
        # The agent reads it as the unprivileged model user.
        host_patch.chmod(0o644)
        yield host_patch
