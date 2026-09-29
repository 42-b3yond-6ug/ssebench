from abc import ABC, abstractmethod


class DockerLayerMixin(ABC):
    @abstractmethod
    def docker_image(self, base: str | None) -> str: ...
