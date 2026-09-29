"""The local LiteLLM proxy: the Docker Compose stack in `deploy/compose/`.

Every Compose call goes through `compose()`, so `ssebench run`, `ssebench proxy` and the just
recipes agree on the project name, the host port and the image registry. The network and URLs are
derived from the project name, which lets stacks with different names run side by side.
"""

import logging
import os
import subprocess
import time

import httpx

from ssebench import paths, settings
from ssebench.pipe import REGISTRY

logger = logging.getLogger(__name__)

SERVICE = "litellm"
CONTAINER_PORT = 4000
REQUIRED_SECRETS = ("LITELLM_MASTER_KEY", "POSTGRES_PASSWORD")


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


def check_secrets() -> None:
    for name in REQUIRED_SECRETS:
        _ = settings.require(name)


def up() -> None:
    """Start the stack. `compose up` recreates the proxy container when its `.env` changed."""
    check_secrets()
    logger.info(f"Starting the LiteLLM proxy (project {settings.compose_project()}, {host_url()})")
    compose("up", "--detach")


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
