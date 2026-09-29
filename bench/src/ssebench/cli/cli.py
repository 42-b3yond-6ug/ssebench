"""SSEBench CLI with subcommands for running benchmarks and building images."""

import argparse
import logging
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from ssebench import doctor, paths, settings, stack
from ssebench.agents import Agent
from ssebench.extensions import (
    DEFAULT_TOOL_LAYER,
    Command,
    ExtensionError,
    command_names,
    get_tool_layer,
    load_commands,
)
from ssebench.models import Model
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRuner
from ssebench.tasks import CatalogError, CatalogTask, LocalTask, Task, load_catalog
from ssebench.version import VERSION

from . import dataset
from .build import build_case_image, get_tasks

logger = logging.getLogger(__name__)

BUILTIN_COMMANDS = ("run", "build-case", "dataset", "proxy", "doctor")


class RunArgs(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.model: str
        self.agent: str
        self.task: str
        self.local: str
        self.catalog: str
        self.mode: Literal["sidecar", "sandbox"]
        self.tool_layer: str | None
        self.timeout: int
        self.difficulty: int
        self.keep_container: bool
        self.egress: Literal["restricted", "open"]


def cmd_run(args: argparse.Namespace) -> int:
    """Run a benchmark."""
    if args.tool_layer is not None and args.mode != "sandbox":
        logger.error("--tool-layer applies to sandbox mode only")
        return 1
    tool_layer = args.tool_layer or DEFAULT_TOOL_LAYER
    # Reject an unknown or broken layer before starting the proxy.
    try:
        _ = get_tool_layer(tool_layer)
    except ExtensionError as e:
        logger.error(e)
        return 1

    task: Task
    try:
        task = (
            LocalTask(args.task, Path(args.local)) if args.local else CatalogTask(load_catalog(args.catalog), args.task)
        )
    except (CatalogError, LookupError) as e:
        logger.error(e)
        return 1

    try:
        stack.up()
        stack.wait_healthy()
    except TimeoutError as e:
        logger.error(e)
        return 1
    except subprocess.CalledProcessError as e:
        logger.error(f"Could not start the LiteLLM proxy: {e}")
        return 1

    # Run the experiment
    model = Model(args.model)
    agent = Agent(args.agent, task_name=task.name)
    timeout = args.timeout
    difficulty = args.difficulty
    keep_container = args.keep_container
    egress = args.egress
    runner: BenchmarkSandboxRunner | BenchmarkSidecarRuner
    match args.mode:
        case "sandbox":
            runner = BenchmarkSandboxRunner(model, agent, task, timeout, difficulty, keep_container, tool_layer, egress)
        case "sidecar":
            runner = BenchmarkSidecarRuner(model, agent, task, timeout, difficulty, keep_container, egress)
        case _:
            logger.error(f"Unknown mode: {args.mode}")
            return 1
    try:
        runner.build()
    except CatalogError as e:
        logger.error(e)
        return 1
    runner.run()
    return 0


def cmd_proxy(args: argparse.Namespace) -> int:
    """Manage the local LiteLLM proxy."""
    try:
        match args.action:
            case "up":
                stack.up(rebuild=args.rebuild)
                stack.wait_healthy()
            case "build":
                _ = stack.build(stack.config_hash(), force=args.rebuild)
            case "down":
                stack.down()
            case _:
                logger.error(f"Unknown action: {args.action}")
                return 1
    except TimeoutError as e:
        logger.error(e)
        return 1
    except subprocess.CalledProcessError as e:
        logger.error(f"docker compose failed: {e}")
        return 1
    return 0


def cmd_build_case(args: argparse.Namespace) -> int:
    """Build case images."""
    benchmarks_dir = Path(args.benchmarks).resolve() if args.benchmarks else paths.default_dataset_dir()
    tasks = get_tasks(benchmarks_dir, args.tasks)

    if not tasks:
        logger.error("No tasks found")
        return 1

    logger.info(f"Found {len(tasks)} tasks to build")

    successful = []
    failed = []

    for task in tasks:
        if build_case_image(task, args.force):
            successful.append(task)
        else:
            failed.append(task)

    logger.info(f"Build summary: {len(successful)} succeeded, {len(failed)} failed")

    if failed:
        logger.error("Failed tasks:")
        for task in failed:
            logger.error(f"  - {task.name}")
        return 1

    return 0


def requested_extensions(argv: Sequence[str]) -> list[Command]:
    """Import only the extension commands this invocation can use.

    A built-in command imports none, so a slow or broken extension cannot affect it.
    """
    requested = argv[0] if argv and not argv[0].startswith("-") else None
    if requested in BUILTIN_COMMANDS:
        return []
    if requested in command_names():
        return load_commands(requested, reserved=BUILTIN_COMMANDS)
    # Help, no command or an unknown one: list every extension command.
    return load_commands(reserved=BUILTIN_COMMANDS)


def main(argv: Sequence[str] | None = None):
    argv = sys.argv[1:] if argv is None else list(argv)
    # The `ssebench` console script enters here, not through __main__; without a handler the
    # progress messages would be dropped. A no-op when logging is already configured.
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="SSEBench CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"ssebench {VERSION}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ==================== run subcommand ====================
    run_parser = subparsers.add_parser("run", help="Run a benchmark")
    run_parser.add_argument("--model", type=str, required=True)
    run_parser.add_argument("--agent", type=str, required=True)
    run_parser.add_argument("--task", type=str, required=True)
    run_parser.add_argument(
        "--local", type=str, default="", metavar="DIR", help="Dataset directory to build the task from"
    )
    run_parser.add_argument(
        "--catalog",
        type=str,
        default="",
        metavar="PATH|URL",
        help="Task catalog, used when --local is not given: a manifest.json path or URL, a dataset directory, or "
        "the URL of a catalog service (default: $SSEBENCH_CATALOG, else the bundled pilot manifest)",
    )
    run_parser.add_argument("--mode", choices=["sidecar", "sandbox"], default="sandbox")
    run_parser.add_argument(
        "--tool-layer",
        type=str,
        default=None,
        metavar="NAME",
        help=f"Tool layer to build in sandbox mode (default: {DEFAULT_TOOL_LAYER}); installed extensions can add more",
    )
    run_parser.add_argument("--timeout", type=int, default=3600)
    run_parser.add_argument(
        "--difficulty",
        type=int,
        default=2,
        help="Difficulty level (default: 2 = NO_FUTURE_TEST)",
    )
    run_parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep container after completion (useful with WebUI)",
    )
    run_parser.add_argument(
        "--egress",
        choices=["restricted", "open"],
        default="restricted",
        help=(
            "Agent network egress policy (default: restricted = LiteLLM proxy "
            "only, no internet). Use 'open' for tasks that need network at test "
            "time."
        ),
    )

    # ==================== build-case subcommand ====================
    build_case_parser = subparsers.add_parser("build-case", help="Build case images")
    build_case_parser.add_argument(
        "--benchmarks",
        type=str,
        default=None,
        help="Path to benchmarks directory (default: datasets/pilot in the SSEBench home)",
    )
    build_case_parser.add_argument(
        "--tasks",
        type=str,
        default=None,
        help="Comma-separated list of task names to build",
    )
    build_case_parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild existing images",
    )

    # ==================== dataset subcommand ====================
    dataset.add_parser(subparsers)

    # ==================== proxy subcommand ====================
    proxy_parser = subparsers.add_parser(
        "proxy",
        help="Start, rebuild or stop the local LiteLLM proxy",
        description="`up` rebuilds the proxy image first when models/ changed; `down` keeps the database volume.",
    )
    proxy_parser.add_argument("action", choices=["up", "build", "down"])
    proxy_parser.add_argument("--rebuild", action="store_true", help="Rebuild the proxy image even if it is current")

    # ==================== doctor subcommand ====================
    _ = subparsers.add_parser(
        "doctor",
        help="Check that this host can build and run benchmarks",
        description="Checks Docker, buildx, Compose, free disk, the CPU architecture, .env, "
        "the LiteLLM proxy and the provider keys. Exits non-zero when a required check fails.",
    )

    extensions: dict[str, Command] = {}
    for command in requested_extensions(argv):
        try:
            # argparse cannot remove a subcommand once added, so try the arguments on a scratch parser first.
            command.configure(argparse.ArgumentParser())
        except Exception as e:
            logger.warning(f"Ignoring command {command.name!r}: configure() failed: {e}")
            continue
        command.configure(subparsers.add_parser(command.name, help=command.help, description=command.help))
        extensions[command.name] = command

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Dispatch to appropriate command
    try:
        if args.command == "run":
            sys.exit(cmd_run(args))
        elif args.command == "build-case":
            sys.exit(cmd_build_case(args))
        elif args.command == "dataset":
            sys.exit(args.handler(args))
        elif args.command == "proxy":
            sys.exit(cmd_proxy(args))
        elif args.command == "doctor":
            sys.exit(doctor.main())
        elif args.command in extensions:
            sys.exit(extensions[args.command].run(args))
        else:
            parser.print_help()
            sys.exit(1)
    except (paths.HomeNotFoundError, settings.SettingError) as e:
        logger.error(e)
        sys.exit(1)
