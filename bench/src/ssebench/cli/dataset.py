"""`ssebench dataset`: check a dataset and write the files generated from it."""

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

from ssebench import paths, pipe, stack
from ssebench.dataset import schema, verify
from ssebench.dataset.generate import MANIFEST, InvalidDatasetError, build_manifest, recorded_commit, render_manifest
from ssebench.dataset.validate import validate_dataset


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("dataset", help="Validate a dataset and generate its manifest")
    commands = parser.add_subparsers(dest="dataset_command", metavar="COMMAND", required=True)

    validate = commands.add_parser("validate", help="Check every task folder of a dataset against the task schema")
    _ = validate.add_argument(
        "dir", nargs="?", metavar="DIR", help="Dataset directory (default: datasets/pilot in the SSEBench home)"
    )
    validate.set_defaults(handler=cmd_validate)

    manifest = commands.add_parser("manifest", help="Validate a dataset and write its manifest.json")
    _ = manifest.add_argument(
        "dir", nargs="?", metavar="DIR", help="Dataset directory (default: datasets/pilot in the SSEBench home)"
    )
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

    export = commands.add_parser(
        "schema", help="Write the JSON Schemas of the task config, dataset.yaml and the manifest"
    )
    _ = export.add_argument(
        "-o", "--output", metavar="DIR", help="Output directory (default: datasets/schema in the SSEBench home)"
    )
    _ = export.add_argument("--check", action="store_true", help="Fail if the files are out of date; write nothing")
    export.set_defaults(handler=cmd_schema)

    check = commands.add_parser(
        "verify",
        help="Grade tasks with the reference and dummy agents and check that they grade as sound tasks do",
        description="Runs every selected task twice through `ssebench run`: the reference agent's fix must pass "
        "every check, and the dummy agent's unmodified project must build and pass its functional tests while "
        "every PoC still triggers the bug. Writes one JSON file per task under OUTPUT/tasks/, the run logs under "
        "OUTPUT/logs/, and summary.md and summary.json covering every task result in OUTPUT. Exits 1 when a "
        "task does not grade as expected.",
    )
    _ = check.add_argument("tasks", nargs="*", default=[], metavar="TASK", help="Tasks to verify (default: every task)")
    _ = check.add_argument("--dir", help="Dataset directory (default: datasets/pilot in the SSEBench home)")
    _ = check.add_argument(
        "--changed-since",
        metavar="REV",
        help="Verify the tasks that changed since the merge base of REV and HEAD, including those whose base "
        "image changed under images/base-images",
    )
    _ = check.add_argument(
        "--list", action="store_true", help="Print the selected tasks and their base images as JSON; run nothing"
    )
    _ = check.add_argument("-j", "--jobs", type=int, default=2, help="Tasks to verify in parallel (default: 2)")
    _ = check.add_argument(
        "-o", "--output", default="results/dataset-verify", help="Output directory (default: results/dataset-verify)"
    )
    _ = check.add_argument(
        "--model",
        default=verify.DEFAULT_DUMMY_MODEL,
        help=f"Model of the dummy runs, which make no model calls (default: {verify.DEFAULT_DUMMY_MODEL})",
    )
    _ = check.add_argument("--difficulty", type=int, default=2, help="Difficulty level of the runs (default: 2)")
    _ = check.add_argument("--timeout", type=int, default=3600, help="Time limit of each run's agent and grading")
    _ = check.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Times to repeat a run that ends without a result, as when a build loses the network (default: 0)",
    )
    _ = check.add_argument(
        "--summarize",
        action="store_true",
        help="Write the summary of the task results already in OUTPUT/tasks/; run nothing",
    )
    check.set_defaults(handler=cmd_verify)


def dataset_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    _ = paths.require_checkout("The pilot task folders")
    return paths.default_dataset_dir()


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
    if args.output:
        directory = Path(args.output)
    else:
        directory = paths.require_checkout("The dataset schemas directory") / "datasets" / "schema"
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


def cmd_verify(args: argparse.Namespace) -> int:
    dataset = dataset_dir(args.dir).resolve()
    output = Path(args.output).resolve()
    if args.tasks and args.changed_since:
        print("Name tasks or give --changed-since, not both", file=sys.stderr)
        return 2
    try:
        report = verify.load_tasks(dataset)
        if args.changed_since:
            tasks = verify.changed_tasks(report, args.changed_since)
        else:
            tasks = verify.select_tasks(report, args.tasks)
    except verify.SelectionError as e:
        print(e, file=sys.stderr)
        return 1

    if args.list:
        print(json.dumps([{"task": t.id, "base": t.base} for t in tasks]))
        return 0

    opts = verify.Options(
        dataset=dataset,
        output=output,
        model=args.model,
        difficulty=args.difficulty,
        timeout=args.timeout,
        retries=args.retries,
    )
    if not args.summarize:
        if not tasks:
            print("No task to verify")
            return 0
        # Started once here, so that the parallel runs find it up instead of all starting it.
        try:
            stack.up()
            stack.wait_healthy()
        except (TimeoutError, subprocess.CalledProcessError) as e:
            print(f"Could not start the LiteLLM proxy: {e}", file=sys.stderr)
            return 1
        print(f"Verifying {len(tasks)} task(s), {args.jobs} at a time; logs in {output / 'logs'}", flush=True)
        _ = verify.verify(opts, tasks, args.jobs, progress=lambda line: print(line, flush=True))

    # A summary of named tasks counts a task without a result as failed, as when its CI job broke off.
    named = args.summarize and bool(args.tasks or args.changed_since)
    verdicts = verify.collect_verdicts(output, tasks if named else report.tasks, complete=named)
    if not verdicts:
        print(f"No task results in {output / 'tasks'}", file=sys.stderr)
        return 1
    meta = {
        "dataset": dataset.name,
        "version": report.info.version if report.info else None,
        "commit": _head_commit(dataset),
        "registry": pipe.REGISTRY,
        "difficulty": opts.difficulty,
        "egress": opts.egress,
    }
    summary = verify.write_summary(output, verdicts, f"Dataset verification: {dataset.name}", meta)
    print(summary.read_text())
    print(f"Wrote {summary} and {summary.with_suffix('.json')}")
    return 0 if all(v.ok for v in verdicts) else 1


def _head_commit(directory: Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None
