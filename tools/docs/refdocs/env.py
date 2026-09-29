"""docs/reference/environment.md: every environment variable, from the registry docs/reference/env.yaml.

The registry is the one list of the variables SSEBench reads or sets. `unregistered()` scans the
source for variables it lacks:

- any word that starts with SSE_, SSEBENCH_ or LITELLM_, in every source file;
- names read through the usual APIs of each language (os.environ, os.Getenv, std::env::var,
  process.env, ...), through `os.environ/NAME` in LiteLLM configs, and through `${NAME}` in the
  Compose files.

A name that matches but is not a variable, or a system variable not worth documenting, goes under
`ignore` in the registry, with the reason.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .page import ROOT, PageError, code, table

REGISTRY = ROOT / "docs" / "reference" / "env.yaml"
ENV_EXAMPLE = ROOT / ".env.example"

# What is scanned, relative to the repository root. Task sources under datasets/ are upstream code.
SCAN_DIRS = ["agents", "bench", "catalog", "deploy", "images", "just", "models", "nix", "runtime", "sdk", "tests"]
SCAN_DIRS += ["tools", "webui", ".github"]
SCAN_FILES = ["Justfile", ".env.example", "flake.nix"]
SKIP_DIRS = {"node_modules", ".venv", "target", "dist", "__pycache__", ".pytest_cache"}
# This scanner, whose patterns and docstrings would match themselves.
SKIP_PATHS = {Path("tools/docs")}
SOURCE_SUFFIXES = {".py", ".go", ".rs", ".ts", ".tsx", ".js", ".mjs", ".sh", ".just", ".nix", ".yaml", ".yml", ".toml"}

PREFIXED = re.compile(r"(?<![\w$])(?:SSE|SSEBENCH|LITELLM)_[A-Z0-9_]*[A-Z0-9](?!\w)")
NAME = r"([A-Za-z_][A-Za-z0-9_]*)"
UPPER_NAME = r"([A-Z_][A-Z0-9_]*)"
# Reads of any variable, by file suffix.
READS: dict[str, list[re.Pattern[str]]] = {
    ".py": [
        re.compile(rf"""os\.(?:environ\.get|getenv|environ\.setdefault)\(\s*["']{NAME}["']"""),
        re.compile(rf"""os\.environ\[\s*["']{NAME}["']\s*\]"""),
        re.compile(rf"""settings\.(?:get|require)\(\s*["']{NAME}["']"""),
    ],
    ".go": [
        re.compile(rf"""os\.(?:Getenv|LookupEnv|Setenv)\(\s*"{NAME}"""),
        re.compile(rf"""EnvVars\(\s*"{NAME}"""),
    ],
    ".rs": [re.compile(rf"""env::var(?:_os)?\(\s*"{NAME}""")],
    ".ts": [
        re.compile(rf"""(?:process\.env|Bun\.env|\benv)\.{UPPER_NAME}"""),
        re.compile(rf"""(?:process\.env|Bun\.env)\[\s*["']{NAME}["']\s*\]"""),
    ],
}
READS[".tsx"] = READS[".js"] = READS[".mjs"] = READS[".ts"]
# LiteLLM configs read `os.environ/NAME`, in the model files and in the config generator.
LITELLM_READ = re.compile(rf"os\.environ/{UPPER_NAME}")
# Compose files interpolate ${NAME}, ${NAME:-default} and ${NAME:?error} from the environment.
COMPOSE_READ = re.compile(rf"\$\{{{NAME}(?::?[-?+][^}}]*)?\}}")
ENV_EXAMPLE_NAME = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)=", re.MULTILINE)


@dataclass
class Variable:
    name: str
    sections: list[str]
    used_by: list[str]
    default: str
    description: str


@dataclass
class Registry:
    sections: dict[str, str]
    variables: dict[str, Variable]
    ignore: dict[str, str] = field(default_factory=dict)


def load() -> Registry:
    with REGISTRY.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    sections = {str(k): str(v) for k, v in data["sections"].items()}
    variables: dict[str, Variable] = {}
    problems = []
    for entry in data["variables"]:
        name = entry["name"]
        if name in variables:
            problems.append(f"{name} is listed twice")
        entry_sections = entry["section"] if isinstance(entry["section"], list) else [entry["section"]]
        problems += [f"{name}: unknown section {s!r}" for s in entry_sections if s not in sections]
        variables[name] = Variable(
            name=name,
            sections=entry_sections,
            used_by=list(entry.get("used_by", [])),
            default=str(entry.get("default", "")),
            description=" ".join(str(entry["description"]).split()),
        )
    ignore = {str(k): str(v) for k, v in (data.get("ignore") or {}).items()}
    problems += [f"{name} is both a variable and ignored" for name in ignore if name in variables]
    if problems:
        raise PageError(f"{REGISTRY.relative_to(ROOT)}: {'; '.join(problems)}")
    return Registry(sections, variables, ignore)


def source_files() -> Iterator[Path]:
    for name in SCAN_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for top in SCAN_DIRS:
        for directory, dirs, files in os.walk(ROOT / top):
            here = Path(directory).relative_to(ROOT)
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and here / d not in SKIP_PATHS)
            for name in sorted(files):
                path = Path(directory) / name
                if path.suffix in SOURCE_SUFFIXES or name.startswith("Dockerfile") or name == "Justfile":
                    yield path


def used_names(path: Path) -> set[str]:
    try:
        text = path.read_text()
    except (UnicodeDecodeError, OSError):
        return set()
    names = set(PREFIXED.findall(text)) | set(LITELLM_READ.findall(text))
    for pattern in READS.get(path.suffix, []):
        names.update(pattern.findall(text))
    if path.suffix in {".yaml", ".yml"} and "compose" in path.parts:
        names.update(COMPOSE_READ.findall(text))
    return names


def scan() -> dict[str, list[Path]]:
    """Every variable name found in the source, with the files it appears in."""
    found: dict[str, list[Path]] = {}
    for path in source_files():
        for name in used_names(path):
            found.setdefault(name, []).append(path.relative_to(ROOT))
    return found


def env_example_names() -> list[str]:
    return list(dict.fromkeys(ENV_EXAMPLE_NAME.findall(ENV_EXAMPLE.read_text())))


def unregistered(registry: Registry, found: dict[str, list[Path]]) -> list[str]:
    """Problems: variables in the source or .env.example that the registry lacks."""
    known = registry.variables.keys() | registry.ignore.keys()
    problems = [
        f"{name} (in {', '.join(str(p) for p in sorted(paths)[:3])}) is not in {REGISTRY.relative_to(ROOT)}"
        for name, paths in sorted(found.items())
        if name not in known
    ]
    problems += [
        f"{name} (in .env.example) is not in {REGISTRY.relative_to(ROOT)}"
        for name in env_example_names()
        if name not in registry.variables
    ]
    return problems


def unused(registry: Registry, found: dict[str, list[Path]]) -> list[str]:
    """Problems: registered or ignored names that no scanned file mentions any more."""
    texts = "\n".join(p.read_text(errors="replace") for p in source_files())
    return [
        f"{name} is in {REGISTRY.relative_to(ROOT)} but no source file mentions it"
        for name in [*registry.variables, *registry.ignore]
        if name not in found and not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", texts)
    ]


def check() -> list[str]:
    registry = load()
    found = scan()
    return unregistered(registry, found) + unused(registry, found)


def default_cell(default: str) -> str:
    """A single word as code; anything longer is Markdown already."""
    if not default:
        return "unset"
    return code(default) if " " not in default and "`" not in default else prose_md(default)


def section_table(registry: Registry, *sections: str) -> str:
    rows = [
        [code(v.name), default_cell(v.default), ", ".join(v.used_by), prose_md(v.description)]
        for v in registry.variables.values()
        if any(s in v.sections for s in sections)
    ]
    if not rows:
        raise PageError(f"{REGISTRY.relative_to(ROOT)}: no variables in {', '.join(sections)}")
    return table(["Variable", "Default", "Used by", "Description"], rows)


def prose_md(text: str) -> str:
    """Registry descriptions are Markdown already; only keep them inside one table cell."""
    return text.replace("|", "\\|")


def dotenv_table(registry: Registry) -> str:
    """The variables of .env.example, in its order."""
    names = env_example_names()
    missing = [name for name in names if name not in registry.variables]
    if missing:
        raise PageError(f".env.example has variables that {REGISTRY.relative_to(ROOT)} lacks: {', '.join(missing)}")
    rows = [
        [code(name), default_cell(registry.variables[name].default), prose_md(registry.variables[name].description)]
        for name in names
    ]
    return table(["Variable", "Default", "Description"], rows)


def regions() -> dict[str, str]:
    registry = load()
    problems = check()
    if problems:
        raise PageError("the environment variable registry is incomplete:\n  " + "\n  ".join(problems))
    return {f"env {section}": section_table(registry, section) for section in registry.sections}


def contract_regions() -> dict[str, str]:
    """The container's variables, for the container contract in docs/guides/extension-points.md."""
    return {"env container and runtime": section_table(load(), "container", "runtime")}
