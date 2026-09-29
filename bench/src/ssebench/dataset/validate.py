"""Check that the folders of a dataset are well-formed tasks."""

import posixpath
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from ssebench.tasks.manifest import DatasetInfo
from ssebench.tasks.metadata import TaskMetadata, load_task_metadata

from .dockerfile import REGISTRY_ARG, REGISTRY_PREFIX, Dockerfile, DockerfileError

CONFIG = "sse/config.yaml"
DATASET_INFO = "dataset.yaml"
IMAGE_ROOT = "/ssebench"


@dataclass
class TaskReport:
    """A task folder, with its validated config and Dockerfile when they are valid."""

    path: Path
    metadata: TaskMetadata | None = None
    dockerfile: Dockerfile | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.path.name

    @property
    def base(self) -> str:
        """The base image, relative to the registry."""
        assert self.dockerfile is not None
        return self.dockerfile.base.removeprefix(REGISTRY_PREFIX)


@dataclass
class DatasetReport:
    path: Path
    info: DatasetInfo | None = None
    tasks: list[TaskReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(not t.errors for t in self.tasks)

    def format_errors(self) -> str:
        lines = [f"{self.path}: {e}" for e in self.errors]
        for task in self.tasks:
            if task.errors:
                lines.append(f"{task.id}:")
                lines += [f"  {e}" for e in task.errors]
        return "\n".join(lines)


def task_dirs(dataset: Path) -> list[Path]:
    """Every subdirectory of a dataset is a task, except hidden ones."""
    return sorted(p for p in dataset.iterdir() if p.is_dir() and not p.name.startswith("."))


def validate_dataset(dataset: Path) -> DatasetReport:
    report = DatasetReport(dataset)
    if not dataset.is_dir():
        report.errors.append("not a directory")
        return report

    try:
        with (dataset / DATASET_INFO).open() as f:
            report.info = DatasetInfo.model_validate(yaml.safe_load(f))
    except FileNotFoundError:
        report.errors.append(f"{DATASET_INFO}: missing")
    except (OSError, yaml.YAMLError) as e:
        report.errors.append(f"{DATASET_INFO}: cannot read: {e}")
    except ValidationError as e:
        report.errors += [f"{DATASET_INFO}: {_describe(err)}" for err in e.errors()]

    report.tasks = [validate_task(d) for d in task_dirs(dataset)]
    if not report.tasks:
        report.errors.append("no task folders")

    seen: dict[str, str] = {}
    for task in report.tasks:
        other = seen.setdefault(task.id.lower(), task.id)
        if other != task.id:
            report.errors.append(f"tasks {other} and {task.id} would share the image name case/.../{task.id.lower()}")
    return report


def validate_task(path: Path) -> TaskReport:
    report = TaskReport(path)
    errors = report.errors

    config = path / CONFIG
    try:
        report.metadata = load_task_metadata(config)
    except FileNotFoundError:
        errors.append(f"{CONFIG}: missing")
    except (OSError, yaml.YAMLError) as e:
        errors.append(f"{CONFIG}: cannot read: {e}")
    except ValidationError as e:
        errors += [f"{CONFIG}: {_describe(err)}" for err in e.errors()]

    if report.metadata is not None and report.metadata.id != report.id:
        errors.append(f"{CONFIG}: id: {report.metadata.id!r} must equal the folder name")

    try:
        report.dockerfile = Dockerfile.read(path / "Dockerfile")
    except FileNotFoundError:
        errors.append("Dockerfile: missing")
    except (OSError, DockerfileError) as e:
        errors.append(f"Dockerfile: {e}")
    if report.dockerfile is None:
        return report

    dockerfile = report.dockerfile
    if not dockerfile.base.startswith(REGISTRY_PREFIX):
        errors.append(f"Dockerfile: the last FROM must be {REGISTRY_PREFIX}<base image>, not {dockerfile.base}")
    elif not dockerfile.registry_declared:
        errors.append(f"Dockerfile: FROM uses {REGISTRY_ARG}, but no ARG {REGISTRY_ARG} precedes it")
    elif not pinned(report.base):
        errors.append(f"Dockerfile: the base image must have a version tag or a digest, not {report.base}")
    for copy in dockerfile.copies:
        if not (path / copy.source).exists():
            errors.append(f"Dockerfile: copies {copy.source}, which does not exist")
    if dockerfile.resolve(path, f"{IMAGE_ROOT}/config.yaml") != path / CONFIG:
        errors.append(f"Dockerfile: must copy {CONFIG} to {IMAGE_ROOT}/config.yaml")

    if report.metadata is not None:
        for name, value in _image_paths(report.metadata):
            image_path = posixpath.normpath(posixpath.join(IMAGE_ROOT, value))
            if not image_path.startswith(IMAGE_ROOT + "/"):
                errors.append(f"{CONFIG}: {name}: {value} is outside {IMAGE_ROOT}")
            elif dockerfile.resolve(path, image_path) is None:
                errors.append(f"{CONFIG}: {name}: the Dockerfile puts no file of the task folder at {image_path}")
    return report


def pinned(image: str) -> bool:
    """Whether an image reference names one version: a digest, or a tag other than latest.

    A tag from a build argument without a default is not known until build time, so it does not count.
    """
    if "@" in image:
        return True
    _, colon, tag = image.rpartition("/")[2].partition(":")
    return bool(colon) and tag not in ("", "latest") and "$" not in tag


def _image_paths(m: TaskMetadata) -> list[tuple[str, str]]:
    """Every path in the config, with its location, such as files.poc[0]."""
    singles = {
        "scripts.build": m.scripts.build,
        "scripts.run": m.scripts.run,
        "scripts.test": m.scripts.test,
        "files.patch": m.files.patch,
        "files.future_test": m.files.future_test,
        "files.security_test": m.files.security_test,
        "files.intent_test": m.files.intent_test,
    }
    paths = [(name, value) for name, value in singles.items() if value]
    paths += [(f"files.poc[{i}]", p) for i, p in enumerate(m.files.poc or [])]
    paths += [(f"task_description.crash_report[{i}]", p) for i, p in enumerate(m.task_description.crash_report or [])]
    return paths


def _describe(error: ErrorDetails) -> str:
    location = ".".join(f"[{part}]" if isinstance(part, int) else str(part) for part in error["loc"])
    location = location.replace(".[", "[")
    message = "unknown key" if error["type"] == "extra_forbidden" else error["msg"]
    return f"{location}: {message}" if location else message
