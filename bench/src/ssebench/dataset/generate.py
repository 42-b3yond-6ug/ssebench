"""Generate a dataset's manifest.json from its task folders."""

import json
from pathlib import Path

from ssebench.arch import Arch
from ssebench.tasks.manifest import Check, Manifest, ManifestTask, case_image_name, task_files
from ssebench.tasks.metadata import TaskMetadata

from .validate import DatasetReport, TaskReport, validate_dataset

MANIFEST = "manifest.json"

# Case images are built and verified for amd64 only: many C tasks build with AddressSanitizer for x86-64.
DEFAULT_ARCH: list[Arch] = ["amd64"]


class InvalidDatasetError(Exception):
    def __init__(self, report: DatasetReport):
        super().__init__(report.format_errors())
        self.report = report


def checks(m: TaskMetadata) -> list[Check]:
    """The checks the grader runs for a task, as the daemon derives them from the config."""
    available: list[Check] = []
    if m.scripts.build:
        available.append("build")
    if m.scripts.run and m.files.poc:
        available.append("poc")
    if m.scripts.test:
        available.append("function_test")
    if m.scripts.test and m.files.future_test:
        available.append("intent_test")
    return available


def manifest_task(dataset: str, task: TaskReport) -> ManifestTask:
    assert task.metadata is not None
    m = task.metadata
    return ManifestTask(
        id=task.id,
        language=m.language,
        project=m.project,
        repository=m.repository,
        base=task.base,
        image=case_image_name(dataset, task.id),
        arch=DEFAULT_ARCH,
        checks=checks(m),
        files=task_files(task.path),
        metadata=m,
    )


def build_manifest(dataset_dir: Path, generated_from: str | None = None) -> Manifest:
    """Validate a dataset and describe it.

    Raises:
        InvalidDatasetError: If any task or the dataset.yaml is invalid.
    """
    report = validate_dataset(dataset_dir)
    if not report.ok:
        raise InvalidDatasetError(report)
    assert report.info is not None
    name = dataset_dir.resolve().name
    return Manifest(
        dataset=name,
        version=report.info.version,
        generated_from=generated_from,
        tasks=sorted((manifest_task(name, t) for t in report.tasks), key=lambda t: t.id),
    )


def render_manifest(manifest: Manifest) -> str:
    """The manifest as JSON. The same manifest always renders to the same text."""
    exclude = {"generated_from"} if manifest.generated_from is None else None
    data = manifest.model_dump(mode="json", exclude=exclude)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def recorded_commit(path: Path) -> str | None:
    """The generated_from of an existing manifest file, if it has one."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    value = data.get("generated_from") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None
