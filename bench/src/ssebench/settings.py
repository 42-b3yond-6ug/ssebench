"""Local settings: the process environment first, then `.env` in the workspace.

`ssebench init` and `just setup` write `.env` from `.env.example`, including generated secrets for
the LiteLLM proxy. Reading `.env` here, instead of relying on the caller to export it, makes
`uv run ssebench` behave the same as the just recipes, which load it themselves.
"""

import os
from pathlib import Path

from dotenv import dotenv_values

from ssebench import paths

DEFAULT_COMPOSE_PROJECT = "ssebench"
DEFAULT_LITELLM_PORT = 4000
SETUP_HINT = "Run `ssebench init` (`just setup` in a checkout) to write .env with generated local secrets"


class SettingError(RuntimeError):
    pass


def env_file() -> Path:
    return paths.env_file()


def dotenv() -> dict[str, str]:
    """The variables in `.env`, or nothing when there is no home or no file."""
    try:
        path = env_file()
    except paths.HomeNotFoundError:
        return {}
    if not path.is_file():
        return {}
    return {name: value for name, value in dotenv_values(path).items() if value is not None}


def get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        value = dotenv().get(name)
    return value.strip() if value else default


def require(name: str) -> str:
    value = get(name)
    if not value:
        raise SettingError(f"{name} is not set. {SETUP_HINT}, or set {name} in the environment.")
    return value


def litellm_master_key() -> str:
    return require("LITELLM_MASTER_KEY")


def litellm_port() -> int:
    raw = get("LITELLM_PORT")
    if not raw:
        return DEFAULT_LITELLM_PORT
    if not raw.isdigit() or not 0 < int(raw) < 65536:
        raise SettingError(f"LITELLM_PORT={raw!r} is not a TCP port number")
    return int(raw)


def compose_project() -> str:
    return get("COMPOSE_PROJECT_NAME", DEFAULT_COMPOSE_PROJECT)
