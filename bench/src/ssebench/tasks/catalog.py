"""Tasks from a catalog: a dataset manifest read from a file, a URL or a catalog service.

`--catalog` or `$SSEBENCH_CATALOG` names the catalog, and the bundled pilot manifest is the
default, so listing and selecting tasks needs no network. A location that ends in `.json` is the
manifest itself; any other location is a directory, or the base URL of a catalog service
(`ssebench-catalog serve`), and the manifest is its `manifest.json`.

A dataset directory may also hold an `images.lock.json`, which pins the published case image of each
task by digest; `$SSEBENCH_IMAGES_LOCK` names another lock, by path or URL.
"""

import logging
import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import final, override
from urllib.parse import urlsplit, urlunsplit

import requests
from pydantic import ValidationError

from ssebench import paths, settings
from ssebench.pipe import REGISTRY
from ssebench.tasks.manifest import IMAGES_LOCK, ImagesLock, Manifest, ManifestTask, files_digest, task_files
from ssebench.tasks.metadata import TaskMetadata

from .local import docker_build_case
from .task import Task

logger = logging.getLogger(__name__)

CATALOG_ENV = "SSEBENCH_CATALOG"
IMAGES_LOCK_ENV = "SSEBENCH_IMAGES_LOCK"
MANIFEST = "manifest.json"
HTTP_TIMEOUT = 30


class CatalogError(RuntimeError):
    """The catalog cannot be read, or a task's case image cannot be obtained."""


def bundled_manifest() -> Path:
    """The pilot dataset's manifest that ships with SSEBench, the catalog when none is configured.

    A checkout has it in `datasets/pilot`; an installed wheel carries a copy, and no task folders.

    Raises:
        paths.HomeNotFoundError: If there is no SSEBench home to find it in.
    """
    return paths.default_dataset_dir() / MANIFEST


def catalog_location(value: str | None = None) -> str:
    """The configured catalog: `value` (from --catalog), else the SSEBENCH_CATALOG setting, else the bundled manifest."""
    return (value or "").strip() or settings.get(CATALOG_ENV) or str(bundled_manifest())


def is_url(location: str) -> bool:
    return urlsplit(location).scheme in ("http", "https")


def manifest_location(location: str) -> str:
    """The manifest file or URL that a catalog location refers to."""
    if is_url(location):
        url = urlsplit(location)
        if url.path.endswith(".json"):
            return location
        return urlunsplit(url._replace(path=url.path.rstrip("/") + "/" + MANIFEST))
    path = Path(location).expanduser()
    return str(path / MANIFEST if path.is_dir() else path)


def read_text(location: str, what: str) -> str:
    """The text of a file or URL.

    Raises:
        CatalogError: If it cannot be read. `what` names it in the message.
    """
    try:
        if is_url(location):
            response = requests.get(location, timeout=HTTP_TIMEOUT)
            _ = response.raise_for_status()
            return response.text
        return Path(location).read_text()
    except (OSError, requests.RequestException) as e:
        raise CatalogError(f"Cannot read the {what} at {location}: {e}") from e


def images_lock_location(catalog_location: str) -> str | None:
    """The images lock that goes with a catalog: `$SSEBENCH_IMAGES_LOCK`, else the file next to a local manifest."""
    configured = settings.get(IMAGES_LOCK_ENV)
    if configured:
        return configured
    if is_url(catalog_location):
        return None
    sibling = Path(catalog_location).parent / IMAGES_LOCK
    return str(sibling) if sibling.is_file() else None


@dataclass(frozen=True)
class Catalog:
    location: str
    """Path or URL of the manifest."""
    manifest: Manifest

    def task(self, task_id: str) -> ManifestTask:
        """
        Raises:
            LookupError: If the catalog has no such task.
        """
        for entry in self.manifest.tasks:
            if entry.id == task_id:
                return entry
        raise LookupError(f"Task {task_id} is not in the catalog at {self.location}")

    def task_folder(self, entry: ManifestTask) -> Path | None:
        """A local folder of the task whose files match the manifest, to build its case image from."""
        candidates: list[Path] = []
        if not is_url(self.location):
            candidates.append(Path(self.location).parent)
        try:
            candidates.append(paths.datasets_dir() / self.manifest.dataset)
        except paths.HomeNotFoundError:
            pass
        for dataset in dict.fromkeys(c.resolve() for c in candidates):
            folder = dataset / entry.id
            if not folder.is_dir():
                continue
            if entry.files is not None and task_files(folder) != entry.files:
                logger.warning(f"{folder} differs from task {entry.id} in the catalog, so it is not used")
                continue
            return folder
        return None

    def case_image(self, entry: ManifestTask) -> str:
        """The name that a task's case image has in the local Docker store: its published name and the dataset version."""
        return f"{REGISTRY}/{entry.image}:{self.manifest.version}"

    def image_ref(self, entry: ManifestTask) -> str:
        """The reference to pull a task's case image by: its digest when the images lock pins one, else its tag.

        Raises:
            CatalogError: If the images lock cannot be read or is not valid.
        """
        digest = self.locked_digest(entry)
        return self.case_image(entry) if digest is None else f"{REGISTRY}/{entry.image}@{digest}"

    @cached_property
    def images_lock(self) -> ImagesLock | None:
        """The lock that pins this dataset version's published images, if there is one.

        Raises:
            CatalogError: If the lock cannot be read or is not valid.
        """
        location = images_lock_location(self.location)
        if location is None:
            return None
        try:
            lock = ImagesLock.model_validate_json(read_text(location, "images lock"))
        except ValidationError as e:
            raise CatalogError(f"{location} is not a valid images lock: {e}") from e
        if (lock.dataset, lock.version) != (self.manifest.dataset, self.manifest.version):
            logger.warning(
                f"{location} is for {lock.dataset} {lock.version}, not {self.manifest.dataset} "
                f"{self.manifest.version}; pulling the case images by tag instead"
            )
            return None
        return lock

    def locked_digest(self, entry: ManifestTask) -> str | None:
        """The digest that the images lock pins for a task, if it was built from the task files the manifest lists.

        Raises:
            CatalogError: If the lock cannot be read or is not valid.
        """
        lock = self.images_lock
        locked = lock.images.get(entry.id) if lock else None
        if locked is None:
            return None
        if entry.files is not None and files_digest(entry.files) != locked.files_sha256:
            logger.warning(
                f"The images lock pins task {entry.id} to an image built from other files than the manifest lists; "
                "pulling the image by tag instead"
            )
            return None
        return locked.digest


def load_catalog(value: str | None = None) -> Catalog:
    """Read the catalog that `value`, $SSEBENCH_CATALOG or the default names; see `catalog_location`.

    Raises:
        CatalogError: If the manifest cannot be read or is not valid.
        paths.HomeNotFoundError: If no catalog is configured and there is no SSEBench home.
    """
    location = manifest_location(catalog_location(value))
    text = read_text(location, "catalog")
    try:
        manifest = Manifest.model_validate_json(text)
    except ValidationError as e:
        raise CatalogError(f"{location} is not a valid dataset manifest: {e}") from e
    return Catalog(location, manifest)


@final
class CatalogTask(Task):
    """
    A task from a catalog. Its case image is pulled from `$SSEBENCH_REGISTRY`, by digest when the
    dataset's images lock pins one and by the dataset version tag otherwise. When the pull fails,
    or with `build_locally`, the image is built from a local copy of the task folder, if there is one.
    """

    def __init__(self, catalog: Catalog, name: str, build_locally: bool = False):
        """
        Args:
            build_locally: Build the case image from the task folder instead of pulling it.

        Raises:
            LookupError: If the catalog has no such task.
            CatalogError: If the images lock is invalid, or `build_locally` is set and there is no task folder.
        """
        self.name = name
        self.catalog = catalog
        self.entry = catalog.task(name)
        self.build_locally = build_locally
        # Whatever the image is pulled or built as, it is tagged with this name locally.
        self.docker_image_name = catalog.case_image(self.entry)
        self.digest = None if build_locally else catalog.locked_digest(self.entry)
        if build_locally and catalog.task_folder(self.entry) is None:
            raise CatalogError(
                f"Cannot build the case image of task {name}: there is no local copy of it. "
                "Run from an SSEBench checkout, or build from a dataset with --local DIR."
            )

    @override
    def docker_image(self, base: str | None) -> str:
        assert base is None  # case images have no base
        self._prepare()
        return self.docker_image_name

    def _prepare(self) -> None:
        """
        Raises:
            CatalogError: If the image can be neither pulled nor built from a local task folder.
            subprocess.CalledProcessError: If the local build fails.
        """
        source = self.docker_image_name if self.digest is None else self.catalog.image_ref(self.entry)
        if not self.build_locally:
            logger.info(f"Pulling case image {source}...")
            if subprocess.run(["docker", "pull", source]).returncode == 0:
                if source != self.docker_image_name:
                    _ = subprocess.run(["docker", "tag", source, self.docker_image_name], check=True)
                return
        folder = self.catalog.task_folder(self.entry)
        if folder is None:
            raise CatalogError(
                f"Cannot pull {source}, and there is no local copy of task {self.name} "
                "to build it from. Check SSEBENCH_REGISTRY, or run the task from its dataset with --local DIR."
            )
        if not self.build_locally:
            logger.warning(f"Cannot pull {source}; building it from {folder} instead")
        docker_build_case(folder, self.docker_image_name)

    @override
    def case_image_exists(self) -> bool:
        """Catalog images are pulled on demand; treat them as always available."""
        return True

    @override
    def task_folder(self) -> Path | None:
        return self.catalog.task_folder(self.entry)

    @override
    def get_task_metadata(self) -> TaskMetadata:
        return self.entry.metadata
