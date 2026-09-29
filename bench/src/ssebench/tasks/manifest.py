"""Schema of a dataset's `manifest.json` and of the `dataset.yaml` it is generated with.

`ssebench dataset manifest` writes the manifest; `datasets/schema/manifest.schema.json` is exported
from these models. Image names in the manifest carry no registry: clients prepend `$SSEBENCH_REGISTRY/`.
"""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .metadata import TASK_ID_PATTERN, TaskMetadata

Check = Literal["build", "poc", "function_test", "intent_test"]
Arch = Literal["amd64", "arm64"]

VERSION_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetInfo(_Model):
    """A dataset's `dataset.yaml`, next to its task folders."""

    model_config = ConfigDict(title="SSEBench dataset info")

    version: str = Field(pattern=VERSION_PATTERN, description="Dataset version, such as pilot-v1.")


class ManifestTask(_Model):
    """One task of the dataset."""

    id: str = Field(pattern=TASK_ID_PATTERN, max_length=128, description="Task ID, the name of the task's folder.")
    language: str = Field(description="Language of the project, from the task config.")
    project: str = Field(description="Upstream project, from the task config.")
    repository: str = Field(description="URL of the upstream repository, from the task config.")
    base: str = Field(
        min_length=1,
        description="Base image of the case image, relative to the registry, with its pinned version: the last "
        "FROM of the task's Dockerfile without ${SSEBENCH_REGISTRY}/, such as base-generic-go:1.0.0.",
    )
    image: str = Field(
        min_length=1, description="Case image, relative to the registry: case/<dataset>/<id>, lowercase."
    )
    arch: list[Arch] = Field(min_length=1, description="Platforms the task runs on.")
    checks: list[Check] = Field(
        description="Checks the grader can run for the task, in the order it runs them: build (scripts.build), "
        "poc (scripts.run with files.poc, the security check), function_test (scripts.test), and intent_test "
        "(scripts.test with files.future_test applied)."
    )
    files: dict[str, Sha256] | None = Field(
        default=None,
        description="SHA-256 of every file in the task folder, by path relative to the folder, sorted by path.",
    )
    metadata: TaskMetadata = Field(description="The task config, validated, with every key present.")


class Manifest(_Model):
    """The machine-readable list of a dataset's tasks."""

    model_config = ConfigDict(title="SSEBench dataset manifest")

    dataset: str = Field(pattern=TASK_ID_PATTERN, description="Dataset name, the name of its folder.")
    version: str = Field(pattern=VERSION_PATTERN, description="Dataset version, from dataset.yaml.")
    generated_from: str | None = Field(
        default=None, description="Commit of the SSEBench repository the manifest was generated from, if recorded."
    )
    tasks: list[ManifestTask] = Field(description="The tasks, sorted by id.")


def task_files(task_dir: Path) -> dict[str, str]:
    """The `files` of a task's manifest entry: the SHA-256 of every file in its folder, sorted by path."""
    paths = sorted((p.relative_to(task_dir).as_posix(), p) for p in task_dir.rglob("*") if p.is_file())
    return {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in paths}
