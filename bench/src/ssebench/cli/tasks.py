"""`ssebench tasks`: list the tasks of a catalog or of a local dataset."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ssebench.dataset.generate import InvalidDatasetError, build_manifest
from ssebench.pipe import REGISTRY
from ssebench.tasks import Catalog, CatalogError, load_catalog
from ssebench.tasks.catalog import CATALOG_ENV, MANIFEST
from ssebench.tasks.manifest import ManifestTask

CATALOG_HELP = (
    "Task catalog: a manifest.json path or URL, a dataset directory, or the URL of a catalog service "
    f"(default: ${CATALOG_ENV}, else the bundled pilot manifest)"
)


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("tasks", help="List the tasks of a catalog or a local dataset")
    commands = parser.add_subparsers(dest="tasks_command", metavar="COMMAND", required=True)

    listing = commands.add_parser("list", help="List the tasks of a catalog or a local dataset")
    source = listing.add_mutually_exclusive_group()
    _ = source.add_argument("--catalog", metavar="PATH|URL", help=CATALOG_HELP)
    _ = source.add_argument("--local", metavar="DIR", help="Dataset directory: list its task folders instead")
    _ = listing.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON array of the tasks without files and metadata, with image names prefixed by the registry "
        "and the case image tagged with the dataset version, or named by its digest when the images lock pins it",
    )
    listing.set_defaults(handler=cmd_list)


def summary(task: ManifestTask, image: str) -> dict[str, Any]:
    """A task as the catalog service's GET /tasks returns it; `image` is the reference of its case image."""
    data = task.model_dump(mode="json", exclude={"files", "metadata"})
    data["base"] = f"{REGISTRY}/{task.base}"
    data["image"] = image
    return data


def cmd_list(args: argparse.Namespace) -> int:
    try:
        if args.local:
            catalog = Catalog(str(Path(args.local) / MANIFEST), build_manifest(Path(args.local)))
        else:
            catalog = load_catalog(args.catalog)
        manifest = catalog.manifest
        images = {t.id: catalog.image_ref(t) for t in manifest.tasks}
    except InvalidDatasetError as e:
        print(e.report.format_errors(), file=sys.stderr)
        print(f"{args.local}: not a valid dataset", file=sys.stderr)
        return 1
    except CatalogError as e:
        print(e, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([summary(t, images[t.id]) for t in manifest.tasks], indent=2, ensure_ascii=False))
        return 0
    rows = [("ID", "LANGUAGE", "PROJECT")] + [(t.id, t.language, t.project) for t in manifest.tasks]
    widths = [max(len(row[i]) for row in rows) for i in range(2)]
    for task_id, language, project in rows:
        print(f"{task_id:<{widths[0]}}  {language:<{widths[1]}}  {project}")
    return 0
