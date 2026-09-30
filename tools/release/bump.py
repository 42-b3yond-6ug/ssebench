#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Set the SSEBench version, or check that every component carries it.

VERSION at the repository root holds the one version of every component, in
SemVer form. Python metadata needs its PEP 440 form, so the Python projects
carry that instead:

    VERSION         Python (PEP 440)
    1.2.0           1.2.0
    1.2.0-rc.1      1.2.0rc1       (also alpha.N -> aN, beta.N -> bN)
    1.2.0-dev       1.2.0.dev0

Usage:
    bump.py 1.2.0-rc.1   write VERSION and every version field, refresh the lockfiles
    bump.py --check      exit 1 if a version field or a lockfile disagrees with VERSION

The Helm chart takes VERSION as it is, both as its own version and as the appVersion
that its image tags default to.

Datasets are versioned on their own (for example in datasets/*/manifest.json);
this tool never reads or writes anything under datasets/.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"

# SemVer restricted to the forms that PEP 440 can express one to one, so that
# the Python version maps back to exactly one VERSION.
SEMVER = re.compile(
    r"(?P<release>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
    r"(?:-(?:(?P<pre>alpha|beta|rc)\.(?P<num>0|[1-9]\d*)|(?P<dev>dev)))?"
)
PEP440_PRE = {"alpha": "a", "beta": "b", "rc": "rc"}

# Compose files whose SSEBench images carry the version as their tag.
COMPOSE_FILES = ["deploy/compose/docker-compose.yaml", "deploy/compose/demo.yaml"]

# The Helm chart, whose version and appVersion are both VERSION.
CHART_FILE = "deploy/helm/ssebench/Chart.yaml"
COMPOSE_IMAGE = re.compile(r"(?m)^(\s*image:\s*\$\{SSEBENCH_REGISTRY[^}]*\}/[\w./-]+?)(?::([\w.-]+))?\s*$")


def pep440(version: str) -> str:
    m = SEMVER.fullmatch(version)
    if m is None:
        raise ValueError(
            f"{version!r} is not a supported version: use X.Y.Z, X.Y.Z-alpha.N, X.Y.Z-beta.N, X.Y.Z-rc.N or X.Y.Z-dev"
        )
    if m["pre"]:
        return f"{m['release']}{PEP440_PRE[m['pre']]}{m['num']}"
    if m["dev"]:
        return f"{m['release']}.dev0"
    return m["release"]


def read_version() -> str:
    version = VERSION_FILE.read_text().strip()
    pep440(version)
    return version


@dataclass
class Field:
    """One place that states the version, in the form `expected` derives from VERSION."""

    path: Path
    label: str
    read: Callable[[], str | None]
    write: Callable[[str], None] | None
    expected: Callable[[str], str]

    def where(self) -> str:
        return f"{self.path.relative_to(ROOT)}: {self.label}"


def _glob_members(patterns: list[str], manifest: str) -> list[Path]:
    members: set[Path] = set()
    for pattern in patterns:
        members.update(p for p in ROOT.glob(pattern) if (p / manifest).is_file())
    return sorted(members)


def _toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def _table_key_writer(path: Path, table: str, key: str) -> Callable[[str], None]:
    """Replace `key = "..."` inside `[table]` of a TOML file, keeping the rest of the file as is."""

    def write(value: str) -> None:
        lines = path.read_text().splitlines(keepends=True)
        in_table = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("["):
                in_table = stripped == f"[{table}]"
                continue
            if in_table and (m := re.match(rf'(\s*{re.escape(key)}\s*=\s*)"[^"]*"', line)):
                lines[i] = f'{m[1]}"{value}"' + line[m.end() :]
                path.write_text("".join(lines))
                return
        raise SystemExit(f"{path.relative_to(ROOT)}: no {key} in [{table}]")

    return write


def _json_version_writer(path: Path) -> Callable[[str], None]:
    def write(value: str) -> None:
        text, n = re.subn(r'(?m)^(  "version":\s*)"[^"]*"', rf'\g<1>"{value}"', path.read_text(), count=1)
        if n != 1:
            raise SystemExit(f'{path.relative_to(ROOT)}: add a top-level "version" field')
        path.write_text(text)

    return write


def _bun_lock() -> dict:
    # bun.lock is JSON with trailing commas.
    text = (ROOT / "bun.lock").read_text()
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def _bun_lock_writer(workspace: str) -> Callable[[str], None]:
    """Set a workspace's version in bun.lock the way bun writes it.

    bun ignores these fields when it checks a lockfile and only refreshes them
    when it re-resolves, so `bun install` alone would leave them stale.
    """

    def write(value: str) -> None:
        path = ROOT / "bun.lock"
        entry = re.compile(
            rf'(?m)^(    "{re.escape(workspace)}": \{{\n      "name": "[^"]*",\n)(      "version": "[^"]*",\n)?'
        )
        text, n = entry.subn(lambda m: f'{m[1]}      "version": "{value}",\n', path.read_text(), count=1)
        if n != 1:
            raise SystemExit(f"bun.lock: no workspace {workspace}; run `bun install` first")
        path.write_text(text)

    return write


def python_fields() -> Iterator[Field]:
    patterns = _toml(ROOT / "pyproject.toml")["tool"]["uv"]["workspace"]["members"]
    members = _glob_members(patterns, "pyproject.toml")
    lock = {p["name"]: p for p in _toml(ROOT / "uv.lock")["package"]}
    for member in members:
        path = member / "pyproject.toml"
        name = re.sub(r"[-_.]+", "-", _toml(path)["project"]["name"]).lower()
        yield Field(
            path,
            "[project] version",
            lambda path=path: _toml(path)["project"].get("version"),
            _table_key_writer(path, "project", "version"),
            pep440,
        )
        yield Field(
            ROOT / "uv.lock",
            f"{name} version",
            lambda name=name: lock.get(name, {}).get("version"),
            None,
            pep440,
        )


def rust_fields() -> Iterator[Field]:
    path = ROOT / "Cargo.toml"
    workspace = _toml(path)["workspace"]
    yield Field(
        path,
        "[workspace.package] version",
        lambda: _toml(path)["workspace"]["package"].get("version"),
        _table_key_writer(path, "workspace.package", "version"),
        str,
    )
    # Members inherit the workspace version; the lockfile shows what each one resolved to.
    lock = {p["name"]: p for p in _toml(ROOT / "Cargo.lock")["package"] if "source" not in p}
    for member in _glob_members(workspace["members"], "Cargo.toml"):
        name = _toml(member / "Cargo.toml")["package"]["name"]
        yield Field(
            ROOT / "Cargo.lock",
            f"{name} version",
            lambda name=name: lock.get(name, {}).get("version"),
            None,
            str,
        )


def js_fields() -> Iterator[Field]:
    patterns = json.loads((ROOT / "package.json").read_text())["workspaces"]
    for member in _glob_members(patterns, "package.json"):
        path = member / "package.json"
        rel = str(member.relative_to(ROOT))
        yield Field(
            path,
            "version",
            lambda path=path: json.loads(path.read_text()).get("version"),
            _json_version_writer(path),
            str,
        )
        yield Field(
            ROOT / "bun.lock",
            f"workspace {rel} version",
            lambda rel=rel: _bun_lock()["workspaces"].get(rel, {}).get("version"),
            _bun_lock_writer(rel),
            str,
        )


def compose_fields() -> Iterator[Field]:
    for rel in COMPOSE_FILES:
        path = ROOT / rel
        for i, m in enumerate(COMPOSE_IMAGE.finditer(path.read_text())):
            label = f"{m[1].split('}/', 1)[1]} image tag"

            def read(path: Path = path, i: int = i) -> str | None:
                return list(COMPOSE_IMAGE.finditer(path.read_text()))[i][2]

            def write(value: str, path: Path = path, i: int = i) -> None:
                text = path.read_text()
                m = list(COMPOSE_IMAGE.finditer(text))[i]
                path.write_text(f"{text[: m.end(1)]}:{value}{text[m.end(2 if m[2] else 1) :]}")

            yield Field(path, label, read, write, str)


def chart_fields() -> Iterator[Field]:
    path = ROOT / CHART_FILE
    for key in ("version", "appVersion"):
        line = re.compile(rf"(?m)^({key}:[ \t]*)\"?([^\"\s#]*)\"?")

        def read(path: Path = path, line: re.Pattern[str] = line) -> str | None:
            m = line.search(path.read_text())
            return m[2] if m else None

        def write(value: str, path: Path = path, line: re.Pattern[str] = line, key: str = key) -> None:
            text, n = line.subn(lambda m: f"{m[1]}{value}", path.read_text(), count=1)
            if n != 1:
                raise SystemExit(f"{path.relative_to(ROOT)}: no {key}")
            path.write_text(text)

        yield Field(path, key, read, write, str)


def fields() -> list[Field]:
    return [*python_fields(), *rust_fields(), *js_fields(), *compose_fields(), *chart_fields()]


def drift(version: str) -> list[str]:
    problems = []
    for field in fields():
        expected = field.expected(version)
        found = field.read()
        if found != expected:
            problems.append(f"{field.where()} is {found!r}, expected {expected!r}")
    return problems


LOCK_COMMANDS = [
    ["uv", "lock"],
    ["cargo", "update", "--workspace"],
    ["bun", "install", "--frozen-lockfile"],
]


def bump(version: str) -> None:
    for field in fields():
        if field.write is not None:
            field.write(field.expected(version))
    VERSION_FILE.write_text(version + "\n")
    for cmd in LOCK_COMMANDS:
        print("+", " ".join(cmd), flush=True)
        try:
            subprocess.run(cmd, cwd=ROOT, check=True)
        except FileNotFoundError:
            raise SystemExit(
                f"{cmd[0]} is not installed; install it, run `{' '.join(cmd)}` and then `{sys.argv[0]} --check`"
            ) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("version", nargs="?", help="new version, for example 1.2.0-rc.1")
    group.add_argument("--check", action="store_true", help="check every component against VERSION")
    args = parser.parse_args()

    if args.check:
        version = read_version()
        problems = drift(version)
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            print(
                f"\n{len(problems)} version(s) differ from VERSION ({version}); run: just release {version}",
                file=sys.stderr,
            )
            return 1
        print(f"Every component is at {version} (Python {pep440(version)}).")
        return 0

    version = args.version.removeprefix("v")
    try:
        pep440(version)
    except ValueError as e:
        parser.error(str(e))

    old = read_version()
    bump(version)
    problems = drift(version)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    print(f"\nBumped {old} -> {version} (Python {pep440(version)}). Review with `git diff`, then:\n")
    print(f'  git commit -am "chore(release): {version}"\n')
    print("and land that commit on main through a pull request.")
    if not version.endswith("-dev"):
        print("Then tag the commit as it landed on main, and push the tag:\n")
        print(f'  git tag -a v{version} -m "v{version}"')
        print(f"  git push origin v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
