"""Build hook: put the repository's assets in the wheel as `ssebench/_data/`.

The CLI builds images from agent definitions, Dockerfiles and the SDK sources, starts the LiteLLM
proxy from a Compose file, and lists the tasks of the pilot manifest. In a checkout it finds them
in the repository; without one, `ssebench.paths` uses this copy, which has the repository's layout.
The files are copied at build time, so the repository stays the only place they are edited.

An sdist built from the repository carries the files under `src/ssebench/_data/`, so the wheel built
from that sdist finds them in place. A build from a tree that has neither the repository around it
nor a `_data/` directory makes a wheel without the assets, which works from a checkout only.
"""

import sys
import tomllib
from pathlib import Path
from typing import Any, override

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Repository paths, files or directories, that the packaged CLI needs.
INCLUDE = (
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    "agents",
    "deploy/compose/docker-compose.yaml",
    "deploy/compose/demo.yaml",
    "images/common",
    "images/litellm",
    "images/sandbox",
    "images/sidecar-agent",
    "images/sidecar-case",
    "models",
    "runtime/evaluator",
    "runtime/mcp",
    "runtime/plugins",
    # The Python SDK, as the tool and agent Dockerfiles copy it into their workspace.
    "sdk/python/pyproject.toml",
    "sdk/python/README.md",
    "sdk/python/sse",
    # Only the manifest and its license, not the task folders: the case images hold the tasks, and the CLI pulls them.
    "datasets/pilot/manifest.json",
    "datasets/pilot/LICENSE",
)

# Names that never belong in the wheel, wherever they occur.
SKIP_NAMES = frozenset(
    {"__pycache__", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".DS_Store"}
)
SKIP_SUFFIXES = (".pyc", ".pyo")


def repository_root(project_root: Path) -> Path | None:
    """The uv workspace root above the project, the directory that has a `[tool.ssebench]` table."""
    candidate = project_root.parent
    try:
        with (candidate / "pyproject.toml").open("rb") as f:
            tool = tomllib.load(f).get("tool", {})
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return candidate if "ssebench" in tool else None


def data_files(repository: Path) -> dict[Path, str]:
    """The files to package, each with its path below `_data/`.

    Raises:
        FileNotFoundError: If an entry of INCLUDE is missing, so that a moved file is not left out silently.
    """
    files: dict[Path, str] = {}
    for entry in INCLUDE:
        source = repository / entry
        if source.is_file():
            candidates = [source]
        elif source.is_dir():
            candidates = sorted(p for p in source.rglob("*") if p.is_file())
        else:
            raise FileNotFoundError(f"{source} is missing; it is listed in bench/hatch_build.py")
        for path in candidates:
            relative = path.relative_to(repository)
            if SKIP_NAMES.intersection(relative.parts) or path.name.endswith(SKIP_SUFFIXES):
                continue
            files[path] = relative.as_posix()
    return files


class DataHook(BuildHookInterface[Any]):
    PLUGIN_NAME = "custom"

    @override
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        # An editable install runs from the checkout and finds the assets there.
        if version == "editable":
            return
        root = Path(self.root)
        packaged = root / "src" / "ssebench" / "_data"
        repository = repository_root(root)
        if packaged.is_dir() or repository is None:
            if not packaged.is_dir():
                print("ssebench: no repository around the project; the wheel has no packaged assets", file=sys.stderr)
            return

        # An sdist keeps the files inside the package directory; a wheel puts them in site-packages.
        prefix = "src/ssebench/_data" if self.target_name == "sdist" else "ssebench/_data"
        for source, relative in data_files(repository).items():
            build_data["force_include"][str(source)] = f"{prefix}/{relative}"
