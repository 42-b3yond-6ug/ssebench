"""Publish the case images of verified tasks, and pin them by digest in the dataset's images lock.

`publish_task` pushes the image that the verification graded, tagged with the dataset version and
with the version and commit, and records the digest the registry reports. `build_lock` collects
those records into `images.lock.json`, which `ssebench run` reads to pull an image by digest.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from ssebench.tasks.manifest import (
    IMAGES_LOCK,
    Commit,
    Digest,
    ImagesLock,
    LockedImage,
    Sha256,
    case_image_name,
    files_digest,
    task_files,
)

from .generate import DEFAULT_ARCH, build_manifest
from .validate import TaskReport
from .verify import case_image, read_verdict

# The records of published images, next to the verification results in the output directory.
RECORDS = "published"
PUSHED_DIGEST = re.compile(r"\bdigest: (sha256:[0-9a-f]{64})\b")


class PublishError(Exception):
    """A task's image cannot be published."""


class LockError(Exception):
    """The images lock cannot be built or is inconsistent."""


class Publication(BaseModel):
    """A case image that was pushed to a registry; the record `build_lock` reads."""

    model_config = ConfigDict(extra="forbid")

    task: str
    dataset: str
    version: str
    image: str
    """The image relative to the registry, without a tag."""
    tags: list[str]
    digest: Digest
    files_sha256: Sha256
    revision: Commit


@dataclass(frozen=True)
class Target:
    dataset: Path
    """The dataset directory, resolved."""
    version: str
    output: Path
    """The verification output directory, which holds the results and receives the records."""
    registry: str
    revision: str
    """The commit of the SSEBench repository that the dataset is at."""


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=False)


def local_image(image: str) -> tuple[str, str] | None:
    """The ID and the architecture of a local image, or None if there is none."""
    proc = docker("image", "inspect", "--format", "{{.Id}} {{.Architecture}}", image)
    fields = proc.stdout.split()
    return (fields[0], fields[1]) if proc.returncode == 0 and len(fields) == 2 else None


def push(ref: str) -> str:
    """Push an image, and return the digest that the registry reports for it.

    Raises:
        PublishError: If the push fails or does not report a digest.
    """
    proc = docker("push", ref)
    _ = sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        raise PublishError(f"docker push {ref} failed: {proc.stderr.strip()}")
    found = PUSHED_DIGEST.findall(proc.stdout)
    if not found:
        raise PublishError(f"docker push {ref} did not report a digest")
    return found[-1]


def publish_task(target: Target, task: TaskReport) -> Publication:
    """Push the case image that the verification graded, and record it in `target.output`.

    The image is the local build of the task, which must be the image both runs graded. It goes
    to `<registry>/case/<dataset>/<id>` with the tag `<version>-<short commit>`, which no later
    commit reuses, and then with the tag `<version>`, which moves to the newest verified image.
    The caller logs in to the registry.

    Raises:
        PublishError: If the task did not verify, or the local image is not the one that was graded.
    """
    if (verdict := read_verdict(target.output, task.id)) is None:
        raise PublishError(f"{task.id}: there is no verification result in {target.output / 'tasks'}")
    if not verdict.ok:
        raise PublishError(f"{task.id}: it did not verify, so its image is not published: {verdict.failures[0]}")
    graded = {run.image for run in verdict.runs.values()}
    if len(graded) != 1 or None in graded:
        raise PublishError(f"{task.id}: the verification did not record the case image that it graded")

    local = case_image(target.dataset, task.id)
    if (found := local_image(local)) is None:
        raise PublishError(f"{task.id}: there is no local image {local}")
    image_id, arch = found
    if image_id not in graded:
        raise PublishError(f"{task.id}: {local} is not the image that was graded, so it is not published")
    if arch not in DEFAULT_ARCH:
        raise PublishError(f"{task.id}: {local} is for {arch}; the tasks are published for {', '.join(DEFAULT_ARCH)}")

    image = case_image_name(target.dataset.name, task.id)
    tags = [f"{target.version}-{target.revision[:7]}", target.version]
    digests: set[str] = set()
    for tag in tags:
        ref = f"{target.registry}/{image}:{tag}"
        if (tagged := docker("tag", local, ref)).returncode != 0:
            raise PublishError(f"docker tag {local} {ref} failed: {tagged.stderr.strip()}")
        digests.add(push(ref))
    if len(digests) != 1:
        raise PublishError(f"{task.id}: the tags {', '.join(tags)} were pushed as different images: {sorted(digests)}")

    publication = Publication(
        task=task.id,
        dataset=target.dataset.name,
        version=target.version,
        image=image,
        tags=tags,
        digest=digests.pop(),
        files_sha256=files_digest(task_files(task.path)),
        revision=target.revision,
    )
    record = target.output / RECORDS / f"{task.id}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    _ = record.write_text(publication.model_dump_json(indent=2) + "\n")
    return publication


# The images lock


def read_records(directory: Path) -> list[Publication]:
    """The records that `publish_task` wrote to `directory`, sorted by task.

    Raises:
        LockError: If a record is not valid.
    """
    records: list[Publication] = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(Publication.model_validate_json(path.read_text()))
        except (OSError, ValidationError) as e:
            raise LockError(f"{path} is not a valid publication record: {e}") from e
    return records


def read_lock(path: Path) -> ImagesLock | None:
    """The lock at `path`, or None if there is no such file.

    Raises:
        LockError: If the file is not a valid lock.
    """
    if not path.is_file():
        return None
    try:
        return ImagesLock.model_validate_json(path.read_text())
    except ValidationError as e:
        raise LockError(f"{path} is not a valid images lock: {e}") from e


def build_lock(dataset: Path, records: Iterable[Publication], previous: ImagesLock | None) -> ImagesLock:
    """The lock of a dataset: the images of `previous` that still match the task files, with `records` on top.

    Raises:
        generate.InvalidDatasetError: If the dataset is not valid.
        LockError: If a record is for another dataset version or for other task files than the ones present.
    """
    manifest = build_manifest(dataset)
    current = {t.id: files_digest(t.files or {}) for t in manifest.tasks}
    images: dict[str, LockedImage] = {}
    if previous is not None and (previous.dataset, previous.version) == (manifest.dataset, manifest.version):
        images = {task: image for task, image in previous.images.items() if current.get(task) == image.files_sha256}
    for record in records:
        if (record.dataset, record.version) != (manifest.dataset, manifest.version):
            raise LockError(
                f"The record of {record.task} is for {record.dataset} {record.version}, "
                f"not {manifest.dataset} {manifest.version}"
            )
        if current.get(record.task) != record.files_sha256:
            raise LockError(f"The record of {record.task} is for other task files than the ones in {dataset}")
        images[record.task] = LockedImage(
            digest=record.digest, files_sha256=record.files_sha256, revision=record.revision
        )
    return ImagesLock(dataset=manifest.dataset, version=manifest.version, images=dict(sorted(images.items())))


def render_lock(lock: ImagesLock) -> str:
    """The lock as JSON. The same lock always renders to the same text."""
    return json.dumps(lock.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def lock_problems(dataset: Path) -> list[str]:
    """What is wrong with the dataset's `images.lock.json`; a lock that lags behind changed tasks is not a problem.

    Raises:
        generate.InvalidDatasetError: If the dataset is not valid.
    """
    manifest = build_manifest(dataset)
    path = dataset / IMAGES_LOCK
    try:
        lock = read_lock(path)
    except LockError as e:
        return [str(e)]
    if lock is None:
        return [f"{path} is missing; run `ssebench dataset lock`"]
    problems: list[str] = []
    if (lock.dataset, lock.version) != (manifest.dataset, manifest.version):
        problems.append(
            f"{path} is for {lock.dataset} {lock.version}, not {manifest.dataset} {manifest.version}; "
            "run `ssebench dataset lock`"
        )
    known = {t.id for t in manifest.tasks}
    problems += [f"{path} pins {task}, which is not a task of the dataset" for task in lock.images if task not in known]
    return problems
