from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from typing import override

from ssebench.arch import ARCHES, Arch, docker_platform, run_arch
from ssebench.pipe import DockerLayerMixin
from ssebench.tasks.metadata import TaskMetadata


class Task(DockerLayerMixin, ABC):
    """
    Abstract base class for benchmark tasks.

    Tasks can be loaded from local benchmarks or remote servers.
    They encapsulate the logic for preparing and running benchmark environments.
    """

    name: str
    docker_image_name: str

    @override
    def describe(self) -> str:
        return f"case image of task {self.name}"

    @abstractmethod
    def get_task_metadata(self) -> TaskMetadata:
        """
        Return the metadata of the current task.
        For local tasks, this fetches the task config yaml file.
        For remote tasks, this fetches from the API.
        """
        pass

    def case_image_matches(self) -> bool | None:
        """
        Return whether the existing case image was built from the task's current files,
        or None when that cannot be told, for example because the image carries no record of them.
        """
        return None

    @abstractmethod
    def case_image_exists(self) -> bool:
        """
        Return whether the case image is already available locally.

        Local tasks check the Docker daemon; remote tasks are considered
        always available after a pull, so they return True unconditionally.
        """
        pass

    def supported_arches(self) -> list[Arch]:
        """The architectures the task's case image is built for, in order of preference; every one when unknown."""
        return list(ARCHES)

    @cached_property
    def arch(self) -> Arch:
        """The architecture that a run builds and runs all of its images for.

        The host's when the task supports it, else the task's first, which runs under emulation.
        """
        return run_arch(self.supported_arches())

    @property
    def platform(self) -> str:
        """`arch` as a Docker platform, such as `linux/amd64`."""
        return docker_platform(self.arch)

    def task_folder(self) -> Path | None:
        """The task's folder on this machine, if there is one."""
        return None

    def task_file(self, relative: Path | str) -> Path | None:
        """A file of the task, by its path in the task config (relative to `sse/`), from the task folder."""
        folder = self.task_folder()
        if folder is None:
            return None
        path = folder / "sse" / relative
        return path if path.is_file() else None
