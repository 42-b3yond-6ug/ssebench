"""Locate the SSEBench home, the directory that holds the assets the CLI builds and runs from.

The home is laid out like the repository: `agents/`, `images/`, `runtime/`, `sdk/`, `models/`,
`deploy/compose/` and `datasets/`, plus the workspace `pyproject.toml` and `uv.lock` that the
image builds copy. Every lookup of those assets goes through this module, so the CLI behaves the
same from any working directory.
"""

import os
import tomllib
from pathlib import Path

HOME_ENV = "SSEBENCH_HOME"


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


def _find_home(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if is_home(directory):
            return directory
    return None


def home() -> Path:
    """Return the SSEBench home.

    The first of: `$SSEBENCH_HOME`; the nearest home at or above the working directory; the
    nearest home above this module, which is the checkout that an in-repo install came from.
    """
    configured = os.environ.get(HOME_ENV)
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            raise HomeNotFoundError(f"{HOME_ENV}={configured} is not a directory")
        return path

    found = _find_home(Path.cwd().resolve()) or _find_home(Path(__file__).resolve().parent)
    if found is None:
        raise HomeNotFoundError(
            f"Cannot find the SSEBench home. Run from inside an SSEBench checkout or set {HOME_ENV} to one."
        )
    return found


def agents_dir() -> Path:
    return home() / "agents"


def datasets_dir() -> Path:
    return home() / "datasets"


def default_dataset_dir() -> Path:
    return datasets_dir() / "pilot"


def compose_file() -> Path:
    return home() / "deploy" / "compose" / "docker-compose.yaml"
