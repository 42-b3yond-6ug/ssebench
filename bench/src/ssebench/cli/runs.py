"""`ssebench runs`: find, watch, stop and remove runs through the runner backend, and list finished ones.

The web UI drives these commands (with `--json`), so it works with any backend without knowing how the
backend reaches its containers. Every command that names a run takes its ID (`--run-id`), never a
container name or ID, which only the backend understands.
"""

import argparse
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

from ssebench.backends import (
    AGENT_LABEL,
    MODEL_LABEL,
    RESULTS_LABEL,
    RUN_ID_LABEL,
    STOP_GRACE_SECONDS,
    TASK_LABEL,
    WEBUI_LABEL,
    Backend,
    BackendError,
    RunInfo,
)
from ssebench.errors import UserError
from ssebench.extensions import ExtensionError, resolve_backend
from ssebench.runner.layout import RESULTS_DIR, SUMMARY_FILE
from ssebench.runner.lifecycle import check_run_id
from ssebench.runner.reference import REFERENCE_RUN_LABEL

EXIT_NOT_FOUND: Final = 3
"""The exit status when no run has the ID that was given."""
EXIT_AMBIGUOUS: Final = 4
"""The exit status when several runs have the ID that was given."""

MAX_SUMMARY_BYTES: Final = 8 * 1024 * 1024
LABEL_PREFIX: Final = "ssebench."
"""Only labels of this family are reported; an image can carry any others."""


class NotFoundError(UserError):
    """No run has the ID."""


class AmbiguousError(UserError):
    """Several runs have the ID, which `--run-id` does not force to be unique across tasks."""


def run_id_arg(value: str) -> str:
    try:
        return check_run_id(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "runs",
        help="List, inspect, stop and remove runs through the runner backend, and list finished runs",
        description="Finds the runs of `ssebench run` on the runner backend by their run ID, the value of "
        f"the `{RUN_ID_LABEL}` label, and reads finished runs from results/. The web UI uses these commands "
        "with --json.",
    )
    commands = parser.add_subparsers(dest="runs_command", metavar="COMMAND", required=True)

    common = argparse.ArgumentParser(add_help=False)
    _ = common.add_argument(
        "--backend",
        default=None,
        metavar="NAME",
        help="The runner backend (default: docker, or $SSEBENCH_BACKEND); installed extensions can add more",
    )
    as_json = argparse.ArgumentParser(add_help=False)
    _ = as_json.add_argument("--json", action="store_true", help="Print JSON instead of text")

    listing = commands.add_parser(
        "list",
        parents=[common, as_json],
        help="List the runs that exist on the backend, running or not",
        description="Lists the runs that the backend has, running or not, that `ssebench run` started.",
    )
    listing.set_defaults(handler=cmd_list)

    inspecting = commands.add_parser(
        "inspect",
        parents=[common, as_json],
        help="Show one run on the backend",
        description=f"Shows the run with that ID. Exits with status {EXIT_NOT_FOUND} if there is none.",
    )
    _ = inspecting.add_argument("run_id", type=run_id_arg, metavar="RUN_ID", help="The run's ID")
    inspecting.set_defaults(handler=cmd_inspect)

    logs = commands.add_parser(
        "logs",
        parents=[common],
        help="Print the output of a run's container",
        description="Prints the container's output, stdout and stderr together, as the backend has it.",
    )
    _ = logs.add_argument("run_id", type=run_id_arg, metavar="RUN_ID", help="The run's ID")
    _ = logs.add_argument("--follow", action="store_true", help="Keep printing until the container exits")
    logs.set_defaults(handler=cmd_logs)

    stop = commands.add_parser(
        "stop",
        parents=[common],
        help="Stop a run's container, leaving it in place",
        description="Asks the run's containers to stop and kills them after the grace period. Stopping a run "
        "that is not running does nothing.",
    )
    _ = stop.add_argument("run_id", type=run_id_arg, metavar="RUN_ID", help="The run's ID")
    _ = stop.add_argument(
        "--grace",
        type=int,
        default=STOP_GRACE_SECONDS,
        metavar="SECONDS",
        help=f"How long the entrypoint may take to clean up before the container is killed (default: {STOP_GRACE_SECONDS})",
    )
    stop.set_defaults(handler=cmd_stop)

    remove = commands.add_parser(
        "remove",
        parents=[common],
        help="Remove a run's containers and volumes, running or not",
        description="Removes what the run left on the backend. The run's results directory stays.",
    )
    _ = remove.add_argument("run_id", type=run_id_arg, metavar="RUN_ID", help="The run's ID")
    remove.set_defaults(handler=cmd_remove)

    endpoint = commands.add_parser(
        "endpoint",
        parents=[common, as_json],
        help="Print the URL at which a port of a running run can be reached from here",
        description="Prints the URL of a port of the run's container that this machine can reach, such as the "
        "daemon's (4263) or the OpenCode server's (4096). Exits with status 1 if the run is not running.",
    )
    _ = endpoint.add_argument("run_id", type=run_id_arg, metavar="RUN_ID", help="The run's ID")
    _ = endpoint.add_argument("port", type=port_arg, metavar="PORT", help="A TCP port of the run's container")
    endpoint.set_defaults(handler=cmd_endpoint)

    execute = commands.add_parser(
        "exec",
        parents=[common],
        help="Run a command in a run's container",
        description="Replaces this process with the command that runs COMMAND in the run's container, with "
        "the standard streams attached. Put -- before COMMAND. Not every backend can do this.",
    )
    _ = execute.add_argument("run_id", type=run_id_arg, metavar="RUN_ID", help="The run's ID")
    _ = execute.add_argument("--user", default=None, metavar="USER", help="Run as this user of the container")
    _ = execute.add_argument("--workdir", default=None, metavar="DIR", help="Working directory in the container")
    _ = execute.add_argument("--tty", action="store_true", help="Allocate a terminal")
    _ = execute.add_argument("--stdin", action="store_true", help="Keep standard input open")
    _ = execute.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME",
        help="Pass the variable NAME with the value it has here (repeatable); the value never appears in a "
        "command line",
    )
    _ = execute.add_argument("argv", nargs="+", metavar="COMMAND", help="The command and its arguments")
    execute.set_defaults(handler=cmd_exec)

    results = commands.add_parser(
        "results",
        parents=[as_json],
        help="List the finished runs in results/, whether or not they still have containers",
        description="Lists the runs whose directory under results/ has a summary.json: the run directories "
        "that `ssebench run` finished, with their grade. It reads files only and needs no backend.",
    )
    _ = results.add_argument(
        "--dir",
        default=RESULTS_DIR,
        metavar="DIR",
        help=f"The results directory (default: {RESULTS_DIR} in the working directory)",
    )
    results.set_defaults(handler=cmd_results)


def port_arg(value: str) -> int:
    if not value.isdigit() or not 0 < int(value) < 65536:
        raise argparse.ArgumentTypeError(f"{value!r} is not a TCP port number")
    return int(value)


# ==================== finding runs ====================


def find_run(backend: Backend, run_id: str) -> RunInfo:
    """The one run of `backend` with that ID.

    Raises:
        NotFoundError: If there is none.
        AmbiguousError: If a task, model or agent reused the ID of another run, which only the
            directory of each keeps apart.
    """
    found = backend.list_runs({RUN_ID_LABEL: run_id})
    if not found:
        raise NotFoundError(f"No run has the ID {run_id}")
    if len(found) > 1:
        raise AmbiguousError(f"{len(found)} runs have the ID {run_id}; remove all but one first")
    return found[0]


def run_json(info: RunInfo) -> dict[str, Any]:
    """A run as the web UI reads it. The container's environment is not part of it: it holds the run's key."""
    labels = {name: value for name, value in info.labels.items() if name.startswith(LABEL_PREFIX)}
    return {
        "run_id": info.run_id,
        "name": info.name,
        "state": info.state,
        "exit_code": info.exit_code,
        "image": info.image,
        "created_at": info.created_at,
        "task": labels.get(TASK_LABEL),
        "model": labels.get(MODEL_LABEL),
        "agent": labels.get(AGENT_LABEL),
        "reference_run": labels.get(REFERENCE_RUN_LABEL) == "true",
        "results_dir": labels.get(RESULTS_LABEL),
        "labels": labels,
    }


def _backend(args: argparse.Namespace) -> Backend:
    try:
        return resolve_backend(args.backend)
    except ExtensionError as e:
        raise UserError(str(e)) from e


def _fail(e: Exception) -> int:
    print(e, file=sys.stderr)
    if isinstance(e, NotFoundError):
        return EXIT_NOT_FOUND
    if isinstance(e, AmbiguousError):
        return EXIT_AMBIGUOUS
    return 1


# ==================== commands ====================


def cmd_list(args: argparse.Namespace) -> int:
    backend = _backend(args)
    try:
        runs = backend.list_runs({WEBUI_LABEL: "true"})
    except BackendError as e:
        return _fail(e)
    # A run without an ID predates run IDs; nothing can name it.
    runs = sorted((info for info in runs if info.run_id), key=lambda info: info.created_at or "", reverse=True)
    if args.json:
        document = {
            "backend": backend.name,
            "supports_exec": backend.supports_exec,
            "runs": [run_json(info) for info in runs],
        }
        print(json.dumps(document, ensure_ascii=False))
        return 0
    print_table(
        ["RUN ID", "STATE", "TASK", "MODEL", "AGENT"],
        [
            [
                i.run_id,
                i.state,
                i.labels.get(TASK_LABEL, ""),
                i.labels.get(MODEL_LABEL, ""),
                i.labels.get(AGENT_LABEL, ""),
            ]
            for i in runs
        ],
    )
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    try:
        info = find_run(_backend(args), args.run_id)
    except (NotFoundError, AmbiguousError, BackendError) as e:
        return _fail(e)
    if args.json:
        print(json.dumps(run_json(info), ensure_ascii=False))
    else:
        for name, value in run_json(info).items():
            if name != "labels":
                print(f"{name}: {value}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    try:
        backend = _backend(args)
        info = find_run(backend, args.run_id)
        for line in backend.logs(info.handle, follow=args.follow):
            sys.stdout.write(line if line.endswith("\n") else line + "\n")
            sys.stdout.flush()
    except BrokenPipeError:
        # The reader went away, which is how a follower ends; keep Python from reporting it at exit.
        _ = os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except (NotFoundError, AmbiguousError, BackendError) as e:
        return _fail(e)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    try:
        backend = _backend(args)
        info = find_run(backend, args.run_id)
        backend.stop(info.handle, args.grace)
    except (NotFoundError, AmbiguousError, BackendError) as e:
        return _fail(e)
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    try:
        backend = _backend(args)
        info = find_run(backend, args.run_id)
        backend.cleanup(info.handle)
        if backend.list_runs({RUN_ID_LABEL: args.run_id}):
            print(f"The run {args.run_id} is still there after cleaning up", file=sys.stderr)
            return 1
    except (NotFoundError, AmbiguousError, BackendError) as e:
        return _fail(e)
    return 0


def cmd_endpoint(args: argparse.Namespace) -> int:
    try:
        backend = _backend(args)
        info = find_run(backend, args.run_id)
        url = backend.endpoint(info.handle, args.port)
    except (NotFoundError, AmbiguousError, BackendError) as e:
        return _fail(e)
    print(json.dumps({"url": url}) if args.json else url)
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    try:
        backend = _backend(args)
        if not backend.supports_exec:
            raise BackendError(f"The {backend.name} backend cannot run commands in a run")
        info = find_run(backend, args.run_id)
        argv = backend.exec_argv(
            info.handle,
            args.argv,
            user=args.user,
            workdir=args.workdir,
            tty=args.tty,
            stdin=args.stdin,
            env_names=args.env,
        )
    except (NotFoundError, AmbiguousError, BackendError) as e:
        return _fail(e)
    sys.stdout.flush()
    try:
        os.execvp(argv[0], argv)
    except OSError as e:
        print(f"Could not run {argv[0]}: {e}", file=sys.stderr)
        return 1


# ==================== finished runs ====================


def _summaries(root: Path) -> Iterator[Path]:
    """The `summary.json` of every run directory under `root`, at any depth: a model name can hold '/'."""
    for directory, subdirectories, files in os.walk(root):
        if SUMMARY_FILE in files:
            # A run directory holds a container's output, not other runs.
            subdirectories.clear()
            yield Path(directory) / SUMMARY_FILE


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def past_run(summary_path: Path) -> dict[str, Any] | None:
    """A finished run from its summary, or None if the file does not parse as one."""
    try:
        if summary_path.stat().st_size > MAX_SUMMARY_BYTES:
            return None
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(summary, dict):
        return None
    task = summary.get("task")
    config = summary.get("config")
    patch_result = summary.get("patch_result")
    config = config if isinstance(config, dict) else {}
    directory = summary_path.parent
    run_id = _string(summary.get("run_id")) or directory.name
    if not isinstance(task, dict) or not _string(task.get("id")):
        return None
    try:
        _ = check_run_id(run_id)
    except ValueError:
        return None
    return {
        "run_id": run_id,
        "task": task["id"],
        "model": _string(config.get("model")),
        "agent": _string(config.get("agent")),
        "mode": _string(config.get("mode")),
        "reference_run": config.get("reference_run") is True,
        "status": _string(patch_result.get("status")) if isinstance(patch_result, dict) else None,
        "started_at": _string(summary.get("started_at")),
        "dir": str(directory.resolve()),
    }


def cmd_results(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    runs = [run for path in _summaries(root) if (run := past_run(path)) is not None] if root.is_dir() else []
    runs.sort(key=lambda run: (run["started_at"] or "", run["run_id"]), reverse=True)
    if args.json:
        print(json.dumps({"runs": runs}, ensure_ascii=False))
        return 0
    print_table(
        ["RUN ID", "STATUS", "TASK", "MODEL", "AGENT"],
        [[r["run_id"], r["status"] or "", r["task"], r["model"] or "", r["agent"] or ""] for r in runs],
    )
    return 0


def print_table(header: list[str], rows: list[list[str]]) -> None:
    rows = [header, *rows]
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
