import logging
import os
import subprocess
from pathlib import Path
from typing import final, override

from pydantic import ValidationError

from ssebench.arch import Arch, platform_args
from ssebench.pipe import REGISTRY
from ssebench.tasks.manifest import Manifest, case_image_name, task_files_digest
from ssebench.tasks.metadata import TaskMetadata, load_task_metadata

from .task import Task

FILES_LABEL = "ssebench.task-files"
"""Label of a case image: the digest of the task folder it was built from."""

logger = logging.getLogger(__name__)


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
        self.docker_image_name = f"{REGISTRY}/{case_image_name(self.dataset, name)}"
        assert self._validate()

    @override
    def docker_image(self, base: str | None) -> str:
        assert base is None  # case images have no base
        self._prepare()
        return self.docker_image_name

    def _prepare(self) -> None:
        docker_build_case(self.task_path, self.docker_image_name, self.platform)

    @override
    def supported_arches(self) -> list[Arch]:
        """The `arch` that the dataset's manifest.json lists for the task; every one without a manifest."""
        return manifest_arches(self.task_path.parent / "manifest.json").get(self.name) or super().supported_arches()

    def _validate(self) -> bool:
        """
        Validate that the task configuration and path are valid.

        Returns:
            bool: True if the task path exists and config is loaded.
        """
        return self.task_path.exists()

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
    def task_folder(self) -> Path | None:
        return self.task_path

    @override
    def case_image_matches(self) -> bool | None:
        """Compare the label of the existing case image with the digest of the task folder now."""
        result = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                f'{{{{ index .Config.Labels "{FILES_LABEL}" }}}}',
                self.docker_image_name,
            ],
            capture_output=True,
            text=True,
        )
        built = result.stdout.strip()
        if result.returncode != 0 or not built or built == "<no value>":
            return None
        return built == task_files_digest(self.task_path)

    @override
    def get_task_metadata(self) -> TaskMetadata:
        metadata_filepath = self.task_path / "sse" / "config.yaml"
        if not metadata_filepath.exists():
            metadata_filepath = self.task_path / "config.yaml"
            if not metadata_filepath.exists():
                raise ValueError("Task metadata config.yaml file cannot be found")
        task_metadata = load_task_metadata(metadata_filepath)
        if task_metadata.id != self.name:
            raise ValueError(
                f"{metadata_filepath}: id {task_metadata.id!r} must match the task folder name {self.name!r}"
            )
        return task_metadata


def get_task_path(benchmark_dir: Path, name: str) -> Path:
    if os.path.exists(benchmark_dir / name):
        return benchmark_dir / name
    else:
        raise FileNotFoundError(f"Benchmark task {name} does not exist.")


def manifest_arches(manifest: Path) -> dict[str, list[Arch]]:
    """The `arch` of every task in a dataset manifest; empty when there is no manifest or it cannot be read."""
    if not manifest.is_file():
        return {}
    try:
        return {task.id: task.arch for task in Manifest.model_validate_json(manifest.read_text()).tasks}
    except (OSError, ValidationError) as e:
        logger.warning(f"Cannot read {manifest}, so its tasks are not limited to an architecture: {e}")
        return {}


def docker_build_case(task_path: Path, image: str, platform: str | None = None) -> None:
    """
    Build a task's case image from its folder, for `platform` (`linux/<arch>`) or the Docker host's own.

    Raises:
        subprocess.CalledProcessError: If the Docker build fails.
    """
    logging.info(f"Building case image {image}...")
    _ = subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            *platform_args(platform),
            "--build-arg",
            f"SSEBENCH_REGISTRY={REGISTRY}",
            "--label",
            f"{FILES_LABEL}={task_files_digest(task_path)}",
            "-t",
            image,
            "--load",
            ".",
        ],
        cwd=task_path,
        check=True,
    )
    logging.info(f"Successfully built case image {image}")
