import logging
import subprocess
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import final, override

from ssebench import paths
from ssebench.pipe import REGISTRY, DockerLayerMixin

DOCKER_IMAGE_PREFIX_SANDBOX = f"{REGISTRY}/tool"
DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT = f"{REGISTRY}/runtime"
DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON = f"{REGISTRY}/tool-sidecar"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ToolLayerContext:
    """What a tool layer is told about the run it builds an image for."""

    task_name: str
    """The task ID, for example `gjson-196-bf4efcb`."""
    source_dir: str
    """Absolute path of the project source inside the case image."""
    build_root: Path = field(default_factory=paths.home)
    """The SSEBench home, which holds `images/`, `runtime/` and `sdk/`; the built-in layers use it as build context."""


class ToolLayer(DockerLayerMixin, ABC):
    """The layer that adds the SSEBench runtime to an image.

    In sandbox mode it sits between the case image and the agent image: `docker_image` receives
    the case image as `base` and returns the image the agent layer is built on.
    """

    def __init__(self, context: ToolLayerContext):
        self.context = context


@final
class SandboxToolLayer(ToolLayer):
    @override
    def docker_image(self, base: str | None) -> str:
        if base is None:
            raise RuntimeError("SandboxToolLayer requires a case image as base")

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SANDBOX}/{self.context.task_name.lower()}"

        logger.info(f"Building sandbox image {docker_image_name}...")
        docker_file = self.context.build_root / "images/sandbox/Dockerfile"
        if not docker_file.exists():
            raise FileNotFoundError(f"Sandbox Dockerfile not found at {docker_file}")
        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--build-context",
                f"case-image=docker-image://{base}",
                "--build-arg",
                f"SOURCE_DIR={self.context.source_dir}",
                "-t",
                docker_image_name,
                "-f",
                str(docker_file),
                "--load",
                str(self.context.build_root),
            ],
            check=True,
        )
        logger.info(f"Successfully built sandbox image {docker_image_name}.")
        return docker_image_name


@final
class SidecarToolLayerAgentRuntime(ToolLayer):
    @override
    def docker_image(self, base: str | None) -> str:
        if base is not None:
            raise RuntimeError("SidecarToolLayerAgentRuntime does not accept a base image")

        docker_image_name = DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT

        logger.info(f"Building sidecar agent runtime image {docker_image_name}...")
        docker_file = self.context.build_root / "images/sidecar-agent/Dockerfile"
        if not docker_file.exists():
            raise FileNotFoundError(f"Sidecar agent Dockerfile not found at {docker_file}")
        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "-t",
                docker_image_name,
                "-f",
                str(docker_file),
                "--load",
                str(self.context.build_root),
            ],
            check=True,
        )
        logger.info(f"Successfully built sidecar agent runtime image {docker_image_name}.")
        return docker_image_name


@final
class SidecarToolLayerEnvironment(ToolLayer):
    @override
    def docker_image(self, base: str | None) -> str:
        if base is None:
            raise RuntimeError("SidecarToolLayerEnvironment requires a case image as base")

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON}/{self.context.task_name.lower()}"

        logger.info(f"Building sidecar environment image {docker_image_name}...")
        docker_file = self.context.build_root / "images/sidecar-case/Dockerfile"
        if not docker_file.exists():
            raise FileNotFoundError(f"Sidecar environment Dockerfile not found at {docker_file}")
        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--build-context",
                f"case-image=docker-image://{base}",
                "--build-arg",
                f"SOURCE_DIR={self.context.source_dir}",
                "-t",
                docker_image_name,
                "-f",
                str(docker_file),
                "--load",
                str(self.context.build_root),
            ],
            check=True,
        )
        logger.info(f"Successfully built sidecar environment image {docker_image_name}.")
        return docker_image_name
