"""SSEBench CLI with subcommands for running benchmarks and building images."""

import argparse
import logging
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import requests

from ssebench import paths
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
from ssebench.tasks import LocalTask, RemoteTask
from ssebench.version import VERSION

from .build import build_case_image, get_tasks

logger = logging.getLogger(__name__)

BUILTIN_COMMANDS = ("run", "build-case")


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


def docker_compose_up(compose_dir: str = ".", compose_file: str | None = None) -> None:
    cmd = ["docker", "compose"]
    if compose_file:
        cmd += ["-f", compose_file]
    cmd += ["up", "-d"]

    _ = subprocess.run(
        cmd,
        cwd=compose_dir,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def wait_for_health(
    url: str = "http://localhost:4000/health/liveliness",
    timeout: float = 180.0,
    interval: float = 2.0,
):
    logger.info(f"Waiting for service health at {url}...")
    deadline = time.monotonic() + timeout
    while True:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                logger.info("Service is healthy.")
                return
        except requests.RequestException:
            pass

        if time.monotonic() >= deadline:
            raise TimeoutError("Service did not become healthy in time.")
        time.sleep(interval)


def cmd_run(args: argparse.Namespace) -> int:
    """Run a benchmark."""
    catalog = args.catalog or os.environ.get("SSEBENCH_CATALOG", "")
    if not args.local and not catalog:
        logger.error(
            "No task source: pass --local DIR for a local dataset, "
            "or --catalog URL (or set SSEBENCH_CATALOG) for a catalog server."
        )
        return 1

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

    # Wait until LiteLLM is ready
    compose_file = paths.compose_file()
    try:
        docker_compose_up(compose_file=str(compose_file))
        wait_for_health()
    except TimeoutError as e:
        logger.error(f"timeout: {e}")
        return 1
    except Exception as e:
        logger.error(f"unexpected error: {e}")
        return 1

    # Run the experiment
    model = Model(args.model)
    task = LocalTask(args.task, Path(args.local)) if args.local else RemoteTask(args.task, catalog)
    agent = Agent(args.agent, task_name=task.name)
    timeout = args.timeout
    difficulty = args.difficulty
    keep_container = args.keep_container
    runner: BenchmarkSandboxRunner | BenchmarkSidecarRuner
    match args.mode:
        case "sandbox":
            runner = BenchmarkSandboxRunner(model, agent, task, timeout, difficulty, keep_container, tool_layer)
        case "sidecar":
            runner = BenchmarkSidecarRuner(model, agent, task, timeout, difficulty, keep_container)
        case _:
            logger.error(f"Unknown mode: {args.mode}")
            return 1
    runner.build()
    runner.run()
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
    run_parser.add_argument("--local", type=str, default="", help="Path to a local dataset directory")
    run_parser.add_argument(
        "--catalog",
        type=str,
        default="",
        help="Catalog server URL, used when --local is not given (default: $SSEBENCH_CATALOG)",
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
        elif args.command in extensions:
            sys.exit(extensions[args.command].run(args))
        else:
            parser.print_help()
            sys.exit(1)
    except paths.HomeNotFoundError as e:
        logger.error(e)
        sys.exit(1)
