"""The parts of a task's Dockerfile that the dataset tooling needs: the base image and the files copied in."""

import json
import posixpath
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

REGISTRY_ARG = "SSEBENCH_REGISTRY"
REGISTRY_PREFIX = "${" + REGISTRY_ARG + "}/"

_FROM_RE = re.compile(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?$", re.IGNORECASE)
_ARG_RE = re.compile(r"^ARG\s+(\w+)(?:=(\S*))?$", re.IGNORECASE)
_VAR_RE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


class DockerfileError(ValueError):
    pass


@dataclass(frozen=True)
class Copy:
    """One source of a COPY or ADD from the build context."""

    source: str
    """Path in the build context."""
    destination: str
    """Absolute path in the image; a trailing slash means the source goes inside it."""


@dataclass
class _Stage:
    image: str
    workdir: str = "/"
    copies: list[Copy] = field(default_factory=list)


@dataclass(frozen=True)
class Dockerfile:
    base: str
    """Image of the final stage. Other global ARG defaults are substituted; the registry stays `${SSEBENCH_REGISTRY}`."""
    copies: tuple[Copy, ...]
    """What the final stage copies from the build context, in order."""
    registry_declared: bool
    """Whether a global `ARG SSEBENCH_REGISTRY` precedes the first FROM."""

    @classmethod
    def read(cls, path: Path) -> "Dockerfile":
        return cls.parse(path.read_text())

    @classmethod
    def parse(cls, text: str) -> "Dockerfile":
        args: dict[str, str | None] = {}
        stages: dict[str, _Stage] = {}
        stage: _Stage | None = None

        for line in _instructions(text):
            keyword, _, rest = line.partition(" ")
            keyword = keyword.upper()
            if keyword == "ARG" and stage is None:
                if m := _ARG_RE.match(line):
                    args[m[1]] = m[2].strip("\"'") if m[2] is not None else None
            elif keyword == "FROM":
                m = _FROM_RE.match(line)
                if m is None:
                    raise DockerfileError(f"cannot parse {line!r}")
                image = _expand(m[1], args)
                parent = stages.get(image.lower())
                stage = _Stage(parent.image, parent.workdir, list(parent.copies)) if parent else _Stage(image)
                if m[2]:
                    stages[m[2].lower()] = stage
            elif stage is None:
                continue
            elif keyword == "WORKDIR":
                stage.workdir = posixpath.join(stage.workdir, rest.strip())
            elif keyword in ("COPY", "ADD"):
                stage.copies += _copies(rest, stage.workdir)

        if stage is None:
            raise DockerfileError("no FROM instruction")
        return cls(base=stage.image, copies=tuple(stage.copies), registry_declared=REGISTRY_ARG in args)

    def resolve(self, context: Path, image_path: str) -> Path | None:
        """The file in the build context that ends up at `image_path` in the image, if any."""
        for copy in reversed(self.copies):
            source = context / copy.source
            destination = copy.destination.rstrip("/") or "/"
            if source.is_dir():
                if image_path == destination or image_path.startswith(destination.rstrip("/") + "/"):
                    candidate = source / posixpath.relpath(image_path, destination)
                    if candidate.is_file():
                        return candidate
            elif source.is_file():
                target = posixpath.join(destination, source.name) if copy.destination.endswith("/") else destination
                if image_path == target:
                    return source
        return None


def _instructions(text: str) -> list[str]:
    """Logical lines: continuations joined, blank lines and comments dropped."""
    lines: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        lines.append(pending + line)
        pending = ""
    if pending.strip():
        lines.append(pending.strip())
    return lines


def _expand(value: str, args: dict[str, str | None]) -> str:
    def substitute(m: re.Match[str]) -> str:
        name = m[1] or m[2]
        default = args.get(name)
        if name == REGISTRY_ARG or default is None:
            return "${" + name + "}"
        return default

    return _VAR_RE.sub(substitute, value)


def _copies(rest: str, workdir: str) -> list[Copy]:
    parts: list[str] = json.loads(rest) if rest.lstrip().startswith("[") else shlex.split(rest)
    if any(p.startswith("--from") for p in parts):
        return []
    paths = [p for p in parts if not p.startswith("--")]
    if len(paths) < 2:
        raise DockerfileError(f"cannot parse COPY {rest!r}")
    *sources, destination = paths
    destination = posixpath.join(workdir, destination)
    if len(sources) > 1 and not destination.endswith("/"):
        destination += "/"
    return [Copy(source=posixpath.normpath(s.lstrip("/")), destination=destination) for s in sources if "://" not in s]
