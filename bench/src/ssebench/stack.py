"""The local LiteLLM proxy: the Docker Compose stack in `deploy/compose/`.

Every Compose call goes through `compose()`, so `ssebench run`, `ssebench proxy` and the just
recipes agree on the project name, the host port and the image registry. The network and URLs are
derived from the project name, which lets stacks with different names run side by side.

The proxy image bakes in its configuration from `models/` in the workspace. The image carries a hash
of those files as a label, and `up()` rebuilds the image when the hash no longer matches.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
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


EGRESS_POLICIES = ("restricted", "open")


def network() -> str:
    """The stack's default Compose network: a normal bridge with internet access."""
    return f"{settings.compose_project()}_default"


def agents_network() -> str:
    """The stack's internal network: it reaches the proxy but not the internet."""
    return f"{settings.compose_project()}_agents"


def run_network(egress: str = "restricted") -> str:
    """The network a run container joins for an egress policy.

    `restricted` (the default) keeps agents off the internet so they cannot look up the upstream
    fix; `open` gives them the default bridge. The proxy is on both, as `litellm`.
    """
    if egress not in EGRESS_POLICIES:
        raise ValueError(f"unknown egress policy {egress!r}; expected one of {EGRESS_POLICIES}")
    return network() if egress == "open" else agents_network()


def service_url() -> str:
    """The proxy's URL from a container on the stack's network."""
    return f"http://{SERVICE}:{CONTAINER_PORT}"


def host_url() -> str:
    return f"http://localhost:{settings.litellm_port()}"


def health_url() -> str:
    return f"{host_url()}/health/liveliness"


def config_files() -> dict[str, Path]:
    """The files baked into the LiteLLM image, by their path in its build context: the model
    definitions and the image's own sources."""
    models = [p for p in paths.models_dir().glob("*") if p.suffix in (".yaml", ".yml")]
    image_sources = list((paths.home() / "images" / "litellm").glob("*"))
    return {
        **{f"models/{p.name}": p for p in sorted(models) if p.is_file()},
        **{f"images/litellm/{p.name}": p for p in sorted(image_sources) if p.is_file()},
    }


def config_hash() -> str:
    digest = hashlib.sha256()
    for name, path in sorted(config_files().items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


@contextmanager
def build_context() -> Iterator[Path]:
    """A directory with the LiteLLM image's build context: `config_files()`, laid out for its Dockerfile.

    The models come from the workspace, which is not the directory of the Dockerfile in an installation
    without a checkout.
    """
    with tempfile.TemporaryDirectory(prefix="ssebench-litellm-") as tmp:
        context = Path(tmp)
        for name, path in config_files().items():
            (context / name).parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copy2(path, context / name)
        yield context


def compose_env() -> dict[str, str]:
    """Environment for Compose: `.env`, overridden by the process environment and resolved settings."""
    return {
        **settings.dotenv(),
        **os.environ,
        "SSEBENCH_REGISTRY": REGISTRY,
        "SSEBENCH_ENV_FILE": str(settings.env_file()),
        "SSEBENCH_VERSION": TAG,
        "LITELLM_PORT": str(settings.litellm_port()),
    }


def compose(*args: str, overlays: Sequence[Path] = ()) -> None:
    """Run `docker compose` on the stack, with the Compose files in `overlays` layered over it."""
    files = [paths.compose_file(), *overlays]
    cmd = [
        "docker",
        "compose",
        "--project-name",
        settings.compose_project(),
        *(arg for file in files for arg in ("--file", str(file))),
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
    with build_context() as context:
        _ = subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--load",
                "--file",
                str(context / "images" / "litellm" / "Dockerfile"),
                "--label",
                f"{CONFIG_LABEL}={current}",
                "--tag",
                image(),
                str(context),
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


def down(volumes: bool = False) -> None:
    """Stop the stack. Its database volume is kept unless `volumes` is set."""
    compose("down", *(["--volumes"] if volumes else []))


def is_healthy(timeout: float = 2.0) -> bool:
    try:
        return httpx.get(health_url(), timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


class ProxyError(TimeoutError):
    """The proxy did not become healthy: its container exited, or it did not answer in time.

    A `TimeoutError`, because callers already report that.
    """


# What the proxy or its database log when the volume holds another password than `.env`.
PASSWORD_MISMATCH = (
    "password authentication failed",
    "Authentication failed against database",
    "provided database credentials",
)
LOG_LINES = 25


def _docker_output(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    return (result.stdout + result.stderr).strip() if result.returncode == 0 else ""


def _service_container(service: str) -> tuple[str, str] | None:
    """The ID and state (`running`, `exited`, ...) of a service's container in the stack, if it has one."""
    project = settings.compose_project()
    out = _docker_output(
        "ps",
        "--all",
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--filter",
        f"label=com.docker.compose.service={service}",
        "--format",
        "{{.ID}} {{.State}}",
    )
    line = out.splitlines()[0].split() if out else []
    return (line[0], line[1]) if len(line) == 2 else None


def _log_tail(service: str) -> str:
    found = _service_container(service)
    if found is None:
        return ""
    return "\n".join(_docker_output("logs", "--tail", str(LOG_LINES), found[0]).splitlines()[-LOG_LINES:])


def exited_error(reset: str) -> ProxyError:
    """The error for a proxy container that exited: its last log lines, and the likely cause when known.

    `reset` is the command that removes the stack together with its database volume.
    """
    project = settings.compose_project()
    proxy_log = _log_tail(SERVICE)
    message = f"The LiteLLM proxy container exited before it became healthy (Compose project {project})."
    logs = proxy_log + _log_tail("litellm_db")
    if any(text in logs for text in PASSWORD_MISMATCH):
        message += (
            f"\n\nThe database volume {project}_postgres_data was created with another POSTGRES_PASSWORD than the "
            "one in .env, because Postgres keeps the password it was created with. Put the old password back in "
            f".env, or start with a new database by running `{reset}` (it deletes the proxy's stored keys and "
            "spend records), or give this workspace its own COMPOSE_PROJECT_NAME."
        )
    if proxy_log:
        message += f"\n\nThe end of the proxy's log:\n{proxy_log}"
    return ProxyError(message)


def wait_healthy(timeout: float = 180.0, interval: float = 2.0, reset: str = "ssebench proxy down --volumes") -> None:
    """Wait until the proxy answers; fail at once when its container has exited, since it never restarts."""
    url = health_url()
    logger.info(f"Waiting for the LiteLLM proxy at {url}...")
    deadline = time.monotonic() + timeout
    while not is_healthy():
        found = _service_container(SERVICE)
        if found is not None and found[1] in ("exited", "dead"):
            raise exited_error(reset)
        if time.monotonic() >= deadline:
            raise ProxyError(f"The LiteLLM proxy did not become healthy at {url} within {timeout:.0f}s")
        time.sleep(interval)
    logger.info("The LiteLLM proxy is healthy.")
