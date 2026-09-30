from abc import ABC, abstractmethod


class DockerLayerMixin(ABC):
    @abstractmethod
    def docker_image(self, base: str | None) -> str: ...

    def describe(self) -> str:
        """What an error message calls this layer's image."""
        return f"{type(self).__name__} image"
