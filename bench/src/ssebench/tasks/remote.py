import logging
import subprocess
from typing import cast, final, override

import requests
from pydantic import BaseModel

from ssebench.tasks.metadata import TaskMetadata

from .task import Task


class RemoteTaskConfig(BaseModel):
    id: str
    image_name: str
    base_image: str
    language: str
    dataset: str


@final
class RemoteTask(Task):
    """
    RemoteTask loads a task from a catalog server.

    The task configuration is fetched from a remote server and the
    Docker image is pulled during the prepare() phase.
    """

    def __init__(self, name: str, server: str):
        self.name = name
        self.server = server.rstrip("/")
        self.remote_tasks = get_remote_tasks_list(self.server)

        self.docker_image_name = ""
        for t in self.remote_tasks:
            if t.id == name:
                self.docker_image_name = t.image_name

        assert self._validate()
        self.task_metadata = get_remote_task_metadata(self.name, self.server)

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

    def _validate(self) -> bool:
        """
        Validate that the task configuration was successfully loaded.
        This will always return True since we trust the remote server to provide correct task configuration.

        Returns:
            bool: True if the task config is loaded and has a valid image name.
        """
        assert self.docker_image_name != ""

        return True

    @override
    def case_image_exists(self) -> bool:
        """Remote images are pulled on demand; treat them as always available."""
        return True

    @override
    def get_task_metadata(self) -> TaskMetadata:
        return self.task_metadata


def get_remote_tasks_list(server: str) -> list[RemoteTaskConfig]:
    """
    GET /tasks: expect return a list[RemoteTaskConfig] json.

    Raises:
        requests.RequestException: If the HTTP request fails.
        pydantic.ValidationError: If the response doesn't match list[RemoteTaskConfig] schema.
    """
    endpoint = f"{server}/tasks"
    resp = requests.get(endpoint)
    resp.raise_for_status()
    tasks_data = cast(list[object], resp.json())
    return [RemoteTaskConfig.model_validate(task) for task in tasks_data]


def get_remote_task_metadata(name: str, server: str) -> TaskMetadata:
    """
    GET /tasks/<task_name>/metadata: expect return a TaskMetadata json.

    Raises:
        requests.RequestException: If the HTTP request fails.
        pydantic.ValidationError: If the response doesn't match RemoteTaskConfig schema.
    """
    endpoint = f"{server}/tasks/{name}/metadata"
    resp = requests.get(endpoint)
    resp.raise_for_status()
    return TaskMetadata.model_validate(resp.json())
