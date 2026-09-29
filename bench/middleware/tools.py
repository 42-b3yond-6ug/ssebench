import logging
import subprocess
from abc import ABC
from pathlib import Path
from typing import final, override

from pipe import REGISTRY, DockerLayerMixin

DOCKER_IMAGE_PREFIX_SANDBOX = f"{REGISTRY}/tool"
DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT = f"{REGISTRY}/runtime"
DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON = f"{REGISTRY}/tool-sidecar"

logger = logging.getLogger(__name__)


class ToolLayer(DockerLayerMixin, ABC):
    @override
    def docker_image(self, base: str | None) -> str: ...


@final
class SandboxToolLayer(ToolLayer):
    def __init__(
        self,
        task_name: str,
        source_dir: str,
        build_root: Path = Path("."),
    ):
        self.task_name = task_name
        self.source_dir = source_dir
        self.build_root = build_root

    @override
    def docker_image(self, base: str | None) -> str:
        if base is None:
            raise RuntimeError("SandboxToolLayer requires a case image as base")

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SANDBOX}/{self.task_name.lower()}"

        logger.info(f"Building sandbox image {docker_image_name}...")
        docker_file = self.build_root / "images/sandbox/Dockerfile"
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
                f"SOURCE_DIR={self.source_dir}",
                "-t",
                docker_image_name,
                "-f",
                str(docker_file),
                "--load",
                str(self.build_root),
            ],
            check=True,
        )
        logger.info(f"Successfully built sandbox image {docker_image_name}.")
        return docker_image_name


@final
class SidecarToolLayerAgentRuntime(ToolLayer):
    def __init__(self, build_root: Path = Path(".")):
        self.build_root = build_root

    @override
    def docker_image(self, base: str | None) -> str:
        if base is not None:
            raise RuntimeError("SidecarToolLayerAgentRuntime does not accept a base image")

        docker_image_name = DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT

        logger.info(f"Building sidecar agent runtime image {docker_image_name}...")
        docker_file = self.build_root / "images/sidecar-agent/Dockerfile"
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
                str(self.build_root),
            ],
            check=True,
        )
        logger.info(f"Successfully built sidecar agent runtime image {docker_image_name}.")
        return docker_image_name


@final
class SidecarToolLayerEnvironment(ToolLayer):
    def __init__(
        self,
        task_name: str,
        source_dir: str,
        build_root: Path = Path("."),
    ):
        self.task_name = task_name
        self.source_dir = source_dir
        self.build_root = build_root

    @override
    def docker_image(self, base: str | None) -> str:
        if base is None:
            raise RuntimeError("SidecarToolLayerEnvironment requires a case image as base")

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON}/{self.task_name.lower()}"

        logger.info(f"Building sidecar environment image {docker_image_name}...")
        docker_file = self.build_root / "images/sidecar-case/Dockerfile"
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
                f"SOURCE_DIR={self.source_dir}",
                "-t",
                docker_image_name,
                "-f",
                str(docker_file),
                "--load",
                str(self.build_root),
            ],
            check=True,
        )
        logger.info(f"Successfully built sidecar environment image {docker_image_name}.")
        return docker_image_name
