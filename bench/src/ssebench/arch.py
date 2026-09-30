"""CPU architectures: the platform a run builds and runs its images for, and when that is emulated.

The tool and agent layers build for both architectures, but a case image is built and verified for the
architectures its task lists in the dataset manifest, and the tool layer sits on it. A run therefore
uses one platform for every image and container of the task: the host's own when the task supports it,
else the task's first architecture, which runs under emulation.
"""

import platform
from collections.abc import Sequence
from typing import Literal

Arch = Literal["amd64", "arm64"]
ARCHES: tuple[Arch, ...] = ("amd64", "arm64")

# What `platform.machine()` reports on the hosts that Docker runs on: Linux says x86_64 or aarch64, macOS arm64.
_MACHINES: dict[str, Arch] = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def host_machine() -> str:
    """The CPU architecture of this host as the operating system names it, or `unknown`."""
    return platform.machine().lower() or "unknown"


def host_arch() -> Arch | None:
    """The architecture of this host, or None when SSEBench builds no images for it."""
    return _MACHINES.get(host_machine())


def run_arch(supported: Sequence[Arch]) -> Arch:
    """The architecture to run a task on: the host's when `supported` has it, else the first of `supported`."""
    host = host_arch()
    return host if host is not None and host in supported else supported[0]


def docker_platform(arch: Arch) -> str:
    return f"linux/{arch}"


def platform_args(platform_name: str | None) -> list[str]:
    """The `--platform` option of a `docker` command, or nothing to use the Docker host's own platform."""
    return ["--platform", platform_name] if platform_name else []


def is_emulated(arch: Arch) -> bool:
    """Whether images of `arch` run under emulation on this host."""
    return arch != host_arch()


def emulation_warning(arch: Arch) -> str:
    """What the user is told when images of `arch` run under emulation on this host."""
    return (
        f"This host is {host_machine()}, so tasks that support only {arch} run under {arch} emulation: their case "
        f"image, the tool layer and the agent all build and run as {docker_platform(arch)}. That is slow, and "
        "AddressSanitizer may misbehave under QEMU."
    )
