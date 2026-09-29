import logging
import subprocess
from typing import final, override
from urllib.parse import quote

import requests

from ssebench.tasks.manifest import ManifestTask
from ssebench.tasks.metadata import TaskMetadata

from .task import Task


@final
class RemoteTask(Task):
    """
    RemoteTask loads a task from a catalog server (`ssebench-catalog serve`).

    The server returns the task's manifest entry with image names already
    prefixed by its registry, and the case image is pulled during the
    prepare() phase.
    """

    def __init__(self, name: str, server: str):
        self.name = name
        self.server = server.rstrip("/")
        entry = get_remote_task(name, self.server)
        self.docker_image_name = entry.image
        self.task_metadata = entry.metadata

    @override
    def docker_image(self, base: str | None) -> str:
        assert base is None  # case images have no base
        self._prepare()
        return self.docker_image_name

    def _prepare(self) -> None:
        """
        Pull the Docker image for this task from the remote registry.

        Raises:
            subprocess.CalledProcessError: If the Docker pull fails.
        """
        logging.info(f"Pulling remote image {self.docker_image_name}...")
        _ = subprocess.run(
            ["docker", "pull", self.docker_image_name],
            check=True,
        )
        logging.info(f"Successfully pulled {self.docker_image_name}")

    @override
    def case_image_exists(self) -> bool:
        """Remote images are pulled on demand; treat them as always available."""
        return True

    @override
    def get_task_metadata(self) -> TaskMetadata:
        return self.task_metadata


def get_remote_task(name: str, server: str) -> ManifestTask:
    """
    GET /tasks/<name>: the task's manifest entry, with resolved image names.

    Raises:
        LookupError: If the catalog has no such task.
        requests.RequestException: If the HTTP request fails.
        pydantic.ValidationError: If the response is not a manifest entry.
    """
    resp = requests.get(f"{server}/tasks/{quote(name, safe='')}", timeout=30)
    if resp.status_code == 404:
        raise LookupError(f"Task {name} is not in the catalog at {server}")
    resp.raise_for_status()
    return ManifestTask.model_validate(resp.json())
