"""The local LiteLLM proxy: the Docker Compose stack in `deploy/compose/`.

Every Compose call goes through `compose()`, so `ssebench run`, `ssebench proxy` and the just
recipes agree on the project name, the host port and the image registry. The network and URLs are
derived from the project name, which lets stacks with different names run side by side.

The proxy image bakes in its configuration from `models/`. The image carries a hash of those files
as a label, and `up()` rebuilds the image when the hash no longer matches.
"""

import hashlib
import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

from ssebench import paths, settings
from ssebench.pipe import REGISTRY, TAG

logger = logging.getLogger(__name__)

SERVICE = "litellm"
CONTAINER_PORT = 4000
CONFIG_LABEL = "ssebench.litellm-config"
REQUIRED_SECRETS = ("LITELLM_MASTER_KEY", "POSTGRES_PASSWORD")


def image() -> str:
    """The proxy image; the Compose file names the same one."""
    return f"{REGISTRY}/litellm:{TAG}"


def network() -> str:
    """The Compose network of the stack; run containers join it to reach the proxy."""
    return f"{settings.compose_project()}_default"


def service_url() -> str:
    """The proxy's URL from a container on the stack's network."""
    return f"http://{SERVICE}:{CONTAINER_PORT}"


def host_url() -> str:
    return f"http://localhost:{settings.litellm_port()}"


def health_url() -> str:
    return f"{host_url()}/health/liveliness"


def config_files(home: Path) -> list[Path]:
    """The files baked into the LiteLLM image: the model definitions and the image's own sources."""
    models = [p for p in (home / "models").glob("*") if p.suffix in (".yaml", ".yml")]
    image_sources = list((home / "images" / "litellm").glob("*"))
    return sorted(p for p in [*models, *image_sources] if p.is_file())


def config_hash(home: Path | None = None) -> str:
    home = home or paths.home()
    digest = hashlib.sha256()
    for path in config_files(home):
        digest.update(path.relative_to(home).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def compose_env() -> dict[str, str]:
    """Environment for Compose: `.env`, overridden by the process environment and resolved settings."""
    return {
        **settings.dotenv(),
        **os.environ,
        "SSEBENCH_REGISTRY": REGISTRY,
        "LITELLM_PORT": str(settings.litellm_port()),
    }


def compose(*args: str) -> None:
    cmd = [
        "docker",
        "compose",
        "--project-name",
        settings.compose_project(),
        "--file",
        str(paths.compose_file()),
        *args,
    ]
    _ = subprocess.run(cmd, env=compose_env(), check=True)


def built_config() -> str | None:
    """The config hash the local LiteLLM image was built from, or None when there is no image."""
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", f'{{{{ index .Config.Labels "{CONFIG_LABEL}" }}}}', image()],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    label = result.stdout.strip()
    return "" if label == "<no value>" else label


def check_secrets() -> None:
    for name in REQUIRED_SECRETS:
        _ = settings.require(name)


def build(current: str, force: bool = False) -> bool:
    """Build the LiteLLM image unless it was built from `current`; return whether it was built."""
    built = built_config()
    if built == current and not force:
        return False
    if built is None:
        logger.info(f"Building the LiteLLM image {image()}")
    elif built == current:
        logger.info(f"Rebuilding the LiteLLM image {image()}")
    else:
        logger.info(f"models/ changed since the LiteLLM image {image()} was built; rebuilding it")
    home = paths.home()
    _ = subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "--file",
            str(home / "images" / "litellm" / "Dockerfile"),
            "--label",
            f"{CONFIG_LABEL}={current}",
            "--tag",
            image(),
            str(home),
        ],
        check=True,
    )
    return True


def up(rebuild: bool = False) -> None:
    """Start the stack, rebuilding the proxy first when its configuration changed.

    `compose up` recreates the proxy container when its image or its `.env` changed.
    """
    check_secrets()
    current = config_hash()
    built = build(current, force=rebuild)
    logger.info(f"Starting the LiteLLM proxy (project {settings.compose_project()}, {host_url()})")
    compose("up", "--detach")
    if built:
        logger.info("The LiteLLM proxy now serves the current models/")


def down() -> None:
    """Stop the stack. Its database volume is kept."""
    compose("down")


def is_healthy(timeout: float = 2.0) -> bool:
    try:
        return httpx.get(health_url(), timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


def wait_healthy(timeout: float = 180.0, interval: float = 2.0) -> None:
    url = health_url()
    logger.info(f"Waiting for the LiteLLM proxy at {url}...")
    deadline = time.monotonic() + timeout
    while not is_healthy():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"The LiteLLM proxy did not become healthy at {url} within {timeout:.0f}s")
        time.sleep(interval)
    logger.info("The LiteLLM proxy is healthy.")
