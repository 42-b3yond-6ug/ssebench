"""`ssebench dataset`: check a dataset and write the files generated from it."""

import argparse
import sys
from pathlib import Path

from ssebench import paths
from ssebench.dataset import schema
from ssebench.dataset.validate import validate_dataset


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("dataset", help="Validate a dataset and generate its manifest")
    commands = parser.add_subparsers(dest="dataset_command", metavar="COMMAND", required=True)

    validate = commands.add_parser("validate", help="Check every task folder of a dataset against the task schema")
    _ = validate.add_argument("dir", nargs="?", help="Dataset directory (default: datasets/pilot in the SSEBench home)")
    validate.set_defaults(handler=cmd_validate)

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
