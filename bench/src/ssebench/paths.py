"""Locate the SSEBench home, the directory that holds the assets the CLI builds and runs from.

The home is laid out like the repository: `agents/`, `images/`, `runtime/`, `sdk/`, `models/`,
`deploy/compose/` and `datasets/`, plus the workspace `pyproject.toml` and `uv.lock` that the
image builds copy. Every lookup of those assets goes through this module, so the CLI behaves the
same from any working directory.

Without a checkout, the home is the copy of those assets inside the installed package
(`ssebench/_data/`, made by the wheel build). It is read-only and has only what the CLI needs:
the pilot manifest but no task folders, the SDK, evaluator and MCP sources but not those of the
daemon and the entrypoint. What the user edits or produces, `.env`, `models/` and `results/`,
lives in the workspace, which is the current directory then.
"""

import os
import tomllib
from pathlib import Path

HOME_ENV = "SSEBENCH_HOME"
PACKAGED_DATA = "_data"


class HomeNotFoundError(RuntimeError):
    pass


def is_home(path: Path) -> bool:
    """Whether `path` has a pyproject.toml with a `[tool.ssebench]` table."""
    try:
        with (path / "pyproject.toml").open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = data.get("tool")
    return isinstance(tool, dict) and "ssebench" in tool


def packaged_data() -> Path | None:
    """The assets that the wheel carries, or None when this is not a wheel install."""
    data = Path(__file__).resolve().parent / PACKAGED_DATA
    return data if is_home(data) else None


def _find_home(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if is_home(directory):
            return directory
    return None


def home() -> Path:
    """Return the SSEBench home.

    The first of: `$SSEBENCH_HOME`; the nearest home at or above the working directory; the
    nearest home above this module, which is the checkout that an in-repo install came from; the
    assets packaged with a wheel.
    """
    configured = os.environ.get(HOME_ENV)
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            raise HomeNotFoundError(f"{HOME_ENV}={configured} is not a directory")
        return path

    found = _find_home(Path.cwd().resolve()) or _find_home(Path(__file__).resolve().parent) or packaged_data()
    if found is None:
        raise HomeNotFoundError(
            f"Cannot find the SSEBench home. Run from inside an SSEBench checkout or set {HOME_ENV} to one."
        )
    return found


def is_packaged() -> bool:
    """Whether the home is the assets inside the installed package rather than a checkout."""
    data = packaged_data()
    return data is not None and home() == data


def workspace() -> Path:
    """The directory of `.env`, `models/` and `results/`: the home of a checkout, else the working directory."""
    return Path.cwd().resolve() if is_packaged() else home()


def require_checkout(purpose: str) -> Path:
    """The home, for something that the packaged assets cannot serve, such as task folders.

    Raises:
        HomeNotFoundError: If the home is the packaged assets. `purpose` says what needs the checkout.
    """
    if is_packaged():
        raise HomeNotFoundError(
            f"{purpose} needs an SSEBench checkout, and this installation has none. "
            f"Run from a checkout, set {HOME_ENV} to one, or name the directory explicitly."
        )
    return home()


def env_file() -> Path:
    return workspace() / ".env"


def models_dir() -> Path:
    """The model definitions the LiteLLM proxy is built from: the workspace's, else the packaged ones."""
    own = workspace() / "models"
    return own if own.is_dir() else home() / "models"


def agents_dir() -> Path:
    return home() / "agents"


def datasets_dir() -> Path:
    return home() / "datasets"


def default_dataset_dir() -> Path:
    return datasets_dir() / "pilot"


def compose_file() -> Path:
    return home() / "deploy" / "compose" / "docker-compose.yaml"
