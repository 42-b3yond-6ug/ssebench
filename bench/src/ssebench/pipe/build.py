import shlex
import subprocess

from ssebench.errors import UserError
from ssebench.pipe.interface import DockerLayerMixin


class ImageBuildError(UserError):
    """A layer's image could not be built. Docker has already shown why."""


def build_pipe(pipeline: list[DockerLayerMixin]) -> str:
    """Build the layers in order, each on the image of the one before, and return the last image's name.

    Raises:
        ImageBuildError: If Docker fails to build a layer or cannot be run.
    """
    base: str | None = None
    for layer in pipeline:
        try:
            base = layer.docker_image(base)
        except subprocess.CalledProcessError as e:
            command = shlex.join(str(part) for part in e.cmd[:3]) if isinstance(e.cmd, list) else str(e.cmd)
            raise ImageBuildError(
                f"Building the {layer.describe()} failed: `{command}` exited with status {e.returncode} "
                "(its output is above)"
            ) from e
        except OSError as e:
            raise ImageBuildError(f"Building the {layer.describe()} failed: {e}") from e
    assert base is not None
    return base
