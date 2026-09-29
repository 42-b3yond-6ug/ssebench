"""Load, validate and select the plugins a run installs and runs.

Plugins are declared in ``runtime/plugins/plugins.yaml`` and validated against
``runtime/plugins/schema.json``. The same two files are read by the container
entrypoint, which validates them again at startup; this module is the host side,
used at build time to check the file and to decide which plugins to install and
enable for a run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import yaml

from ssebench import paths

PLUGINS_FILE = "plugins.yaml"
PLUGINS_SCHEMA = "schema.json"


class PluginError(RuntimeError):
    """plugins.yaml is missing a schema, malformed, or does not match the schema."""


@dataclass(frozen=True)
class Plugin:
    name: str
    enabled: bool
    hook: str
    llm: bool
    timeout: int


def plugins_dir() -> Path:
    """The directory that holds plugins.yaml, the schema and the plugin folders."""
    return paths.home() / "runtime" / "plugins"


def load_plugins(directory: Path | None = None) -> list[Plugin]:
    """Read and validate plugins.yaml. A missing file means no plugins.

    Raises PluginError if the file is present but the schema is missing, the
    YAML is malformed, it does not match the schema, or a name is repeated.
    """
    directory = directory or plugins_dir()
    plugins_path = directory / PLUGINS_FILE
    if not plugins_path.is_file():
        return []

    try:
        raw = yaml.safe_load(plugins_path.read_text()) or []
    except yaml.YAMLError as e:
        raise PluginError(f"{PLUGINS_FILE}: {e}") from e

    schema_path = directory / PLUGINS_SCHEMA
    try:
        schema = json.loads(schema_path.read_text())
    except OSError as e:
        raise PluginError(f"{PLUGINS_SCHEMA}: {e}") from e
    try:
        jsonschema.validate(raw, schema)
    except jsonschema.ValidationError as e:
        raise PluginError(f"{PLUGINS_FILE} does not match {PLUGINS_SCHEMA}: {e.message}") from e

    plugins = [Plugin(**entry) for entry in raw]
    seen: set[str] = set()
    for p in plugins:
        if p.name in seen:
            raise PluginError(f"{PLUGINS_FILE}: plugin {p.name!r} is declared twice")
        seen.add(p.name)
    return plugins


def select_plugins(plugins: list[Plugin], requested: list[str] | None) -> tuple[list[Plugin], list[str]]:
    """The plugins a run enables, in plugins.yaml order, and the requested names
    that plugins.yaml does not declare.

    ``requested`` is ``None`` when no ``--plugin`` flag was given, in which case
    the ``enabled`` field decides; otherwise exactly the requested plugins run.
    """
    if requested is None:
        return [p for p in plugins if p.enabled], []

    want = set(requested)
    selected = [p for p in plugins if p.name in want]
    known = {p.name for p in plugins}
    unknown = [name for name in requested if name not in known]
    return selected, unknown


def selected_plugins(requested: list[str] | None, directory: Path | None = None) -> list[Plugin]:
    """Load, validate and select in one step, raising PluginError on any problem,
    including a requested plugin that is not declared.
    """
    plugins = load_plugins(directory)
    selected, unknown = select_plugins(plugins, requested)
    if unknown:
        raise PluginError(f"unknown plugin(s): {', '.join(unknown)}")
    for p in selected:
        run_sh = (directory or plugins_dir()) / p.name / "run.sh"
        if not run_sh.is_file():
            raise PluginError(f"plugin {p.name!r}: no run.sh in {run_sh.parent}")
    return selected
