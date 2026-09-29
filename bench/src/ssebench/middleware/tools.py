import logging
import subprocess
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import final, override

from ssebench import paths, settings
from ssebench.pipe import REGISTRY, TAG, DockerLayerMixin
from ssebench.version import VERSION

DOCKER_IMAGE_PREFIX_SANDBOX = f"{REGISTRY}/tool"
DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT = f"{REGISTRY}/tool-sidecar-agent"
DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON = f"{REGISTRY}/tool-sidecar"

RUNTIME_IMAGE_ENV = "SSEBENCH_RUNTIME_IMAGE"

logger = logging.getLogger(__name__)


def runtime_image() -> str:
    """The published image of this version that holds the daemon and the entrypoint."""
    return f"{REGISTRY}/runtime:{TAG}"


def runtime_build_args(build_root: Path) -> list[str]:
    """`docker buildx build` arguments that take the daemon and the entrypoint from a runtime image.

    The Dockerfiles of the tool layers build both from source unless a `runtime` build context replaces
    that stage. A home without their sources, as in an installation without a checkout, cannot build them
    and uses the published image of this version. `SSEBENCH_RUNTIME_IMAGE` names another image to use in
    either case, which also saves compiling in a checkout.
    """
    configured = settings.get(RUNTIME_IMAGE_ENV)
    if configured:
        return ["--build-context", f"runtime=docker-image://{configured}"]
    if (build_root / "sdk" / "daemon").is_dir() and (build_root / "runtime" / "entrypoint").is_dir():
        return []
    return ["--build-context", f"runtime=docker-image://{runtime_image()}"]


@dataclass(frozen=True, kw_only=True)
class ToolLayerContext:
    """What a tool layer is told about the run it builds an image for."""

    task_name: str
    """The task ID, for example `gjson-196-bf4efcb`."""
    source_dir: str
    """Absolute path of the project source inside the case image."""
    build_root: Path = field(default_factory=paths.home)
    """The SSEBench home, which holds `images/`, `runtime/` and `sdk/`; the built-in layers use it as build context."""
    plugins: tuple[str, ...] = ()
    """Plugins to install into the tool layer, by folder name; empty installs none."""


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

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SANDBOX}/{self.context.task_name.lower()}:{TAG}"

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
                *runtime_build_args(self.context.build_root),
                "--build-arg",
                f"SOURCE_DIR={self.context.source_dir}",
                "--build-arg",
                f"VERSION={VERSION}",
                "--build-arg",
                f"PLUGINS={' '.join(self.context.plugins)}",
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

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT}:{TAG}"

        logger.info(f"Building sidecar agent runtime image {docker_image_name}...")
        docker_file = self.context.build_root / "images/sidecar-agent/Dockerfile"
        if not docker_file.exists():
            raise FileNotFoundError(f"Sidecar agent Dockerfile not found at {docker_file}")
        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                *runtime_build_args(self.context.build_root),
                "--build-arg",
                f"VERSION={VERSION}",
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

        docker_image_name = f"{DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON}/{self.context.task_name.lower()}:{TAG}"

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
                *runtime_build_args(self.context.build_root),
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
