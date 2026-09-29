"""Tasks from a catalog: a dataset manifest read from a file, a URL or a catalog service.

`--catalog` or `$SSEBENCH_CATALOG` names the catalog, and the bundled pilot manifest is the
default, so listing and selecting tasks needs no network. A location that ends in `.json` is the
manifest itself; any other location is a directory, or the base URL of a catalog service
(`ssebench-catalog serve`), and the manifest is its `manifest.json`.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import final, override
from urllib.parse import urlsplit, urlunsplit

import requests
from pydantic import ValidationError

from ssebench import paths, settings
from ssebench.pipe import REGISTRY
from ssebench.tasks.manifest import Manifest, ManifestTask, task_files
from ssebench.tasks.metadata import TaskMetadata

from .local import docker_build_case
from .task import Task

logger = logging.getLogger(__name__)

CATALOG_ENV = "SSEBENCH_CATALOG"
MANIFEST = "manifest.json"
HTTP_TIMEOUT = 30


class CatalogError(RuntimeError):
    """The catalog cannot be read, or a task's case image cannot be obtained."""


def bundled_manifest() -> Path:
    """The pilot dataset's manifest that ships with SSEBench, the catalog when none is configured.

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


def load_catalog(value: str | None = None) -> Catalog:
    """Read the catalog that `value`, $SSEBENCH_CATALOG or the default names; see `catalog_location`.

    Raises:
        CatalogError: If the manifest cannot be read or is not valid.
        paths.HomeNotFoundError: If no catalog is configured and there is no SSEBench home.
    """
    location = manifest_location(catalog_location(value))
    try:
        if is_url(location):
            response = requests.get(location, timeout=HTTP_TIMEOUT)
            _ = response.raise_for_status()
            text = response.text
        else:
            text = Path(location).read_text()
    except (OSError, requests.RequestException) as e:
        raise CatalogError(f"Cannot read the catalog at {location}: {e}") from e
    try:
        manifest = Manifest.model_validate_json(text)
    except ValidationError as e:
        raise CatalogError(f"{location} is not a valid dataset manifest: {e}") from e
    return Catalog(location, manifest)


@final
class CatalogTask(Task):
    """
    A task from a catalog. Its case image is pulled from `$SSEBENCH_REGISTRY`; when the pull
    fails, it is built from a local copy of the task folder, if there is one.
    """

    def __init__(self, catalog: Catalog, name: str):
        self.name = name
        self.catalog = catalog
        self.entry = catalog.task(name)
        self.docker_image_name = f"{REGISTRY}/{self.entry.image}"

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
        logger.info(f"Pulling case image {self.docker_image_name}...")
        if subprocess.run(["docker", "pull", self.docker_image_name]).returncode == 0:
            return
        folder = self.catalog.task_folder(self.entry)
        if folder is None:
            raise CatalogError(
                f"Cannot pull {self.docker_image_name}, and there is no local copy of task {self.name} "
                "to build it from. Check SSEBENCH_REGISTRY, or run the task from its dataset with --local DIR."
            )
        logger.warning(f"Cannot pull {self.docker_image_name}; building it from {folder} instead")
        docker_build_case(folder, self.docker_image_name)

    @override
    def case_image_exists(self) -> bool:
        """Catalog images are pulled on demand; treat them as always available."""
        return True

    @override
    def get_task_metadata(self) -> TaskMetadata:
        return self.entry.metadata
