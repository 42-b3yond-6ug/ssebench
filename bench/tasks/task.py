from abc import ABC, abstractmethod

from pipe import DockerLayerMixin
from tasks.metadata import TaskMetadata


class Task(DockerLayerMixin, ABC):
    """
    Abstract base class for benchmark tasks.

    Tasks can be loaded from local benchmarks or remote servers.
    They encapsulate the logic for preparing and running benchmark environments.
    """

    name: str
    docker_image_name: str

    @abstractmethod
    def get_task_metadata(self) -> TaskMetadata:
        """
        Return the metadata of the current task.
        For local tasks, this fetches the task config yaml file.
        For remote tasks, this fetches from the API.
        """
        pass

    @abstractmethod
    def case_image_exists(self) -> bool:
        """
        Return whether the case image is already available locally.

        Local tasks check the Docker daemon; remote tasks are considered
        always available after a pull, so they return True unconditionally.
        """
        pass
