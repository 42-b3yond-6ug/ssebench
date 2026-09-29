import logging
import os
import subprocess
from pathlib import Path
from typing import final, override

import yaml

from pipe import REGISTRY
from tasks.metadata import TaskMetadata

from .task import Task

# Language mapping from base type
LANGUAGE_MAP = {
    "generic-c": "c",
    "generic-cpp": "cpp",
    "generic-java": "java",
    "generic-python": "python",
    "generic-rust": "rust",
    "generic-go": "go",
    "aixcc-c": "c",
    "aixcc-cpp": "cpp",
}


def _parse_task_id(name: str) -> tuple[str, str]:
    """Parse task_id to extract base image type and project info.

    Format: <base-type>-<project>-<issue_id>
    Example: generic-c-jq-jq_gh_2825

    Returns:
        tuple of (base_type, project)
    """
    parts = name.split("-")

    # Determine base image type (first 1-2 parts)
    if parts[0] == "generic" and len(parts) > 1:
        base_type = f"{parts[0]}-{parts[1]}"
        remaining = parts[2:]
    elif parts[0] == "aixcc" and len(parts) > 1:
        base_type = f"{parts[0]}-{parts[1]}"
        remaining = parts[2:]
    else:
        base_type = parts[0]
        remaining = parts[1:]

    # Extract project name (usually the first part of remaining)
    project = remaining[0] if remaining else "unknown"

    return base_type, project


@final
class LocalTask(Task):
    """
    LocalTask loads a task from a local dataset directory such as `datasets/pilot`.

    The task is loaded from the local filesystem and the Docker image
    is built during the prepare() phase.
    """

    def __init__(self, name: str, localpath: Path):
        self.name = name
        self.task_path = get_task_path(localpath, name)
        self.task_metadata = self.get_task_metadata()
        self.dataset = localpath.resolve().name
        self.docker_image_name = f"{REGISTRY}/case/{self.dataset}/{name}".lower()
        self._base_type, self._project = _parse_task_id(name)
        assert self._validate()

    @override
    def docker_image(self, base: str | None) -> str:
        assert base is None  # case images have no base
        self._prepare()
        return self.docker_image_name

    def _prepare(self) -> None:
        """
        Build the Docker image for this task.

        Raises:
            subprocess.CalledProcessError: If the Docker build fails.
            ValueError: If evaluator can't be found.
        """
        logging.info(f"Building case image {self.docker_image_name}...")
        _ = subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--build-arg",
                f"SSEBENCH_REGISTRY={REGISTRY}",
                "-t",
                self.docker_image_name,
                "--load",
                ".",
            ],
            cwd=self.task_path,
            check=True,
        )
        logging.info(f"Successfully built case image {self.docker_image_name}")

    def _validate(self) -> bool:
        """
        Validate that the task configuration and path are valid.

        Returns:
            bool: True if the task path exists and config is loaded.
        """
        return self.task_path.exists()

    @property
    def base_type(self) -> str:
        """Return the base image type (e.g., 'generic-c', 'aixcc-c')."""
        return self._base_type

    @property
    def base_image_name(self) -> str:
        """Return the base image name for this task."""
        return f"{REGISTRY}/base-{self._base_type}"

    @property
    def project(self) -> str:
        """Return the project name extracted from task_id."""
        return self._project

    @property
    def language(self) -> str:
        """Return the programming language for this task."""
        return LANGUAGE_MAP.get(self._base_type, "unknown")

    @override
    def case_image_exists(self) -> bool:
        """Check if the case image already exists in Docker."""
        result = subprocess.run(
            ["docker", "images", "-q", self.docker_image_name],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    @override
    def get_task_metadata(self) -> TaskMetadata:
        metadata_filepath = self.task_path / "sse" / "config.yaml"
        if not metadata_filepath.exists():
            metadata_filepath = self.task_path / "config.yaml"
            if not metadata_filepath.exists():
                raise ValueError("Task metadata config.yaml file cannot be found")
        with open(metadata_filepath) as f:
            task_metadata = TaskMetadata.model_validate(yaml.safe_load(f))
        return task_metadata


def get_task_path(benchmark_dir: Path, name: str) -> Path:
    if os.path.exists(benchmark_dir / name):
        return benchmark_dir / name
    else:
        raise FileNotFoundError(f"Benchmark task {name} does not exist.")
