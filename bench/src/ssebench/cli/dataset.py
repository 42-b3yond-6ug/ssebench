"""`ssebench dataset`: check a dataset and write the files generated from it."""

import argparse
import difflib
import sys
from pathlib import Path

from ssebench import paths
from ssebench.dataset import schema
from ssebench.dataset.generate import MANIFEST, InvalidDatasetError, build_manifest, recorded_commit, render_manifest
from ssebench.dataset.validate import validate_dataset


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("dataset", help="Validate a dataset and generate its manifest")
    commands = parser.add_subparsers(dest="dataset_command", metavar="COMMAND", required=True)

    validate = commands.add_parser("validate", help="Check every task folder of a dataset against the task schema")
    _ = validate.add_argument("dir", nargs="?", help="Dataset directory (default: datasets/pilot in the SSEBench home)")
    validate.set_defaults(handler=cmd_validate)

    manifest = commands.add_parser("manifest", help="Validate a dataset and write its manifest.json")
    _ = manifest.add_argument("dir", nargs="?", help="Dataset directory (default: datasets/pilot in the SSEBench home)")
    _ = manifest.add_argument(
        "-o", "--output", metavar="FILE", help="Output file, or - for stdout (default: manifest.json in the dataset)"
    )
    _ = manifest.add_argument("--check", action="store_true", help="Fail if the file is out of date; write nothing")
    _ = manifest.add_argument(
        "--generated-from",
        metavar="COMMIT",
        help="Record the repository commit the manifest is generated from (default: none; with --check, the "
        "commit recorded in the file)",
    )
    manifest.set_defaults(handler=cmd_manifest)

    export = commands.add_parser("schema", help="Write the JSON Schemas of the task config and the manifest")
    _ = export.add_argument(
        "-o", "--output", metavar="DIR", help="Output directory (default: datasets/schema in the SSEBench home)"
    )
    _ = export.add_argument("--check", action="store_true", help="Fail if the files are out of date; write nothing")
    export.set_defaults(handler=cmd_schema)


def dataset_dir(arg: str | None) -> Path:
    return Path(arg) if arg else paths.default_dataset_dir()


def cmd_validate(args: argparse.Namespace) -> int:
    dataset = dataset_dir(args.dir)
    report = validate_dataset(dataset)
    if not report.ok:
        print(report.format_errors(), file=sys.stderr)
        invalid = sum(1 for t in report.tasks if t.errors)
        print(f"{dataset}: {invalid} of {len(report.tasks)} tasks are invalid", file=sys.stderr)
        return 1
    print(f"{dataset}: {len(report.tasks)} tasks are valid")
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    dataset = dataset_dir(args.dir)
    output: str | None = args.output
    target = None if output == "-" else Path(output) if output else dataset / MANIFEST
    if args.check and target is None:
        print("--check needs an output file", file=sys.stderr)
        return 2

    commit: str | None = args.generated_from
    if commit is None and args.check and target is not None:
        commit = recorded_commit(target)
    try:
        manifest = build_manifest(dataset, commit)
    except InvalidDatasetError as e:
        print(e.report.format_errors(), file=sys.stderr)
        print(f"{dataset}: not a valid dataset, so no manifest was generated", file=sys.stderr)
        return 1
    text = render_manifest(manifest)

    if target is None:
        _ = sys.stdout.write(text)
    elif args.check:
        current = target.read_text() if target.is_file() else ""
        if current != text:
            diff = difflib.unified_diff(current.splitlines(), text.splitlines(), str(target), "generated", lineterm="")
            print("\n".join(list(diff)[:40]), file=sys.stderr)
            print(f"{target} is out of date; run `ssebench dataset manifest` to update it", file=sys.stderr)
            return 1
        print(f"{target} is up to date")
    else:
        _ = target.write_text(text)
        print(f"wrote {target} with {len(manifest.tasks)} tasks")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    directory = Path(args.output) if args.output else paths.datasets_dir() / "schema"
    if args.check:
        stale = schema.stale_schemas(directory)
        if stale:
            print(
                f"{directory}: out of date: {', '.join(stale)}; run `ssebench dataset schema` to update",
                file=sys.stderr,
            )
            return 1
        return 0
    for path in schema.write_schemas(directory):
        print(f"wrote {path}")
    return 0
