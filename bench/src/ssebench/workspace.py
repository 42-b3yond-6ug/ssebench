"""Scaffold a workspace: the directory that holds `.env`, `models/` and `results/`.

`ssebench init` writes them from the SSEBench home, like `just setup` does in a checkout. Nothing
that exists is changed, so the command is safe to repeat: the Postgres database of the LiteLLM proxy
keeps the password it was created with, and edited model files are the user's.
"""

import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ssebench import paths

GENERATED_SECRETS = ("LITELLM_MASTER_KEY", "POSTGRES_PASSWORD")


@dataclass
class Scaffold:
    """What `scaffold` did, as paths relative to the workspace."""

    written: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)


def render_env(template: str) -> str:
    """`.env.example` with a generated value for each of GENERATED_SECRETS.

    The master key is a bearer token for the local proxy, so it starts with `sk-`, like a LiteLLM key.
    """
    lines: list[str] = []
    for line in template.splitlines():
        name, separator, value = line.partition("=")
        if separator and name in GENERATED_SECRETS and not value:
            line = f"{name}={'sk-' if name == 'LITELLM_MASTER_KEY' else ''}{secrets.token_hex(24)}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def write_env(workspace: Path, result: Scaffold) -> None:
    path = workspace / ".env"
    if path.exists():
        result.kept.append(".env")
        return
    # Owner-only from the first byte: the file holds the proxy's admin key.
    path.touch(mode=0o600)
    _ = path.write_text(render_env(paths.env_example().read_text()))
    result.written.append(".env")


def copy_models(workspace: Path, result: Scaffold) -> None:
    """Copy the model definitions that the workspace does not have yet, so that they can be edited."""
    target = workspace / "models"
    target.mkdir(exist_ok=True)
    for source in sorted((paths.home() / "models").glob("*")):
        if source.suffix not in (".yaml", ".yml") or not source.is_file():
            continue
        name = f"models/{source.name}"
        if (target / source.name).exists():
            result.kept.append(name)
        else:
            _ = shutil.copyfile(source, target / source.name)
            result.written.append(name)


def scaffold(workspace: Path) -> Scaffold:
    """Create `.env` with generated secrets, `models/` and `results/` in `workspace`, keeping what exists."""
    result = Scaffold()
    workspace.mkdir(parents=True, exist_ok=True)
    write_env(workspace, result)
    copy_models(workspace, result)
    results = workspace / "results"
    if results.is_dir():
        result.kept.append("results/")
    else:
        results.mkdir()
        result.written.append("results/")
    return result
