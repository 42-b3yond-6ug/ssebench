"""SSEBench CLI with subcommands for running benchmarks and building images."""

import argparse
import logging
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from ssebench import arch, doctor, paths, settings, stack
from ssebench.agents import Agent
from ssebench.backends import Egress
from ssebench.errors import UserError
from ssebench.extensions import (
    DEFAULT_BACKEND,
    DEFAULT_TOOL_LAYER,
    BackendError,
    Command,
    ExtensionError,
    command_names,
    get_tool_layer,
    load_commands,
    resolve_backend,
)
from ssebench.models import NO_MODEL, Model, NoModel, require_defined
from ssebench.plugins import PluginError, selected_plugins
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner, RunOutcome
from ssebench.runner.layout import new_run_id, run_dir
from ssebench.runner.lifecycle import RUN_ID_LABEL, RunGuard, check_run_id
from ssebench.runner.reference import REFERENCE_AGENT, is_reference_run, reference_patch_path
from ssebench.runner.result import describe_grade
from ssebench.tasks import CatalogError, CatalogTask, LocalTask, Task, load_catalog
from ssebench.version import VERSION

from . import dataset, demo, init, runs, tasks
from .build import build_case_image, get_tasks

logger = logging.getLogger(__name__)

# These agents make no model calls, so a run with them needs no provider key.
KEYLESS_AGENTS = ("dummy", REFERENCE_AGENT)

PREBUILT_ENV = "SSEBENCH_PREBUILT"
EGRESS_ENV = "SSEBENCH_EGRESS"
EGRESS_POLICIES: tuple[Egress, ...] = ("restricted", "open")

BUILTIN_COMMANDS = ("run", "build-case", "dataset", "tasks", "runs", "proxy", "doctor", "init", "demo")


class RunArgs(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.model: str | None
        self.agent: str
        self.task: str
        self.local: str
        self.catalog: str
        self.build: bool
        self.mode: Literal["sidecar", "sandbox"]
        self.tool_layer: str | None
        self.timeout: int
        self.difficulty: int
        self.keep_container: bool
        self.egress: Egress | None
        self.plugin: list[str]
        self.run_id: str | None
        self.backend: str | None
        self.prebuilt: bool
        self.require_pass: bool


def run_id_arg(value: str) -> str:
    try:
        return check_run_id(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def egress_policy(requested: Egress | None) -> Egress:
    """The `--egress` option, else `SSEBENCH_EGRESS`, else restricted."""
    name = requested or settings.get(EGRESS_ENV) or "restricted"
    for policy in EGRESS_POLICIES:
        if name == policy:
            return policy
    raise UserError(f"{EGRESS_ENV}={name!r} is not a network egress policy; use one of: {', '.join(EGRESS_POLICIES)}")


def report_outcome(outcome: RunOutcome) -> None:
    """Print the grade and where the run's files are, on standard output for a script to read."""
    patch = outcome.summary.patch_result
    print(f"Result: {describe_grade(patch)}")
    print(f"Grade: {patch.status}" + (f" ({patch.error_msg})" if patch.status == "error" and patch.error_msg else ""))
    print(f"Run directory: {outcome.directory}")


def cmd_run(args: argparse.Namespace) -> int:
    """Run a benchmark."""
    reference_run = is_reference_run(args.agent)
    if args.model is None and not reference_run:
        logger.error(f"--model is required, except with --agent {REFERENCE_AGENT}")
        return 1
    if reference_run and args.model not in (None, NO_MODEL):
        logger.warning(f"The {REFERENCE_AGENT} agent makes no model calls; ignoring --model {args.model}")

    if args.tool_layer is not None and args.mode != "sandbox":
        logger.error("--tool-layer applies to sandbox mode only")
        return 1
    if args.mode == "sidecar":
        logger.warning("Sidecar mode is experimental; see 'Sandbox and sidecar' in the documentation for its limits")
    tool_layer = args.tool_layer or DEFAULT_TOOL_LAYER
    try:
        egress = egress_policy(args.egress)
    except UserError as e:
        logger.error(e)
        return 1
    prebuilt = bool(getattr(args, "prebuilt", False)) or settings.flag(PREBUILT_ENV)
    if prebuilt and (args.tool_layer is not None or getattr(args, "plugin", None) or getattr(args, "build", False)):
        logger.error("--prebuilt uses images that are already built, so it excludes --tool-layer, --plugin and --build")
        return 1
    # Reject an unknown or broken layer or backend before starting the proxy.
    try:
        _ = get_tool_layer(tool_layer)
        backend = resolve_backend(getattr(args, "backend", None))
        # A backend with a proxy of its own is responsible for it; the local stack is for the others.
        proxy = backend.proxy()
    except (ExtensionError, BackendError) as e:
        logger.error(e)
        return 1

    if getattr(args, "plugin", None) and args.mode != "sandbox":
        logger.error("--plugin applies to sandbox mode only")
        return 1
    # A run selects plugins with --plugin, or enables the ones plugins.yaml
    # marks enabled. Validate the file and the selection before the proxy.
    requested = getattr(args, "plugin", None) or None
    try:
        plugins = selected_plugins(requested)
    except PluginError as e:
        logger.error(e)
        return 1
    plugin_names = [p.name for p in plugins]
    if prebuilt and plugin_names:
        logger.warning(
            f"Prebuilt images carry the plugins they were built with; {', '.join(plugin_names)} (enabled in "
            "plugins.yaml) are not installed by this run"
        )
        plugin_names = []

    task: Task
    try:
        task = (
            LocalTask(args.task, Path(args.local))
            if args.local
            else CatalogTask(load_catalog(args.catalog), args.task, build_locally=getattr(args, "build", False))
        )
    except (CatalogError, LookupError, FileNotFoundError) as e:
        logger.error(e)
        return 1
    if reference_run:
        try:
            _ = reference_patch_path(task)
        except ValueError as e:
            logger.error(e)
            return 1

    # Reject an unknown or broken agent, an unknown model and a missing provider key before the
    # proxy starts or anything is built.
    # A sidecar agent image is built on the task-independent runtime image, so every task shares it.
    agent = Agent(args.agent, task_name=task.name if args.mode == "sandbox" else "sidecar", platform=task.platform)
    if args.model is not None and not reference_run:
        require_defined(args.model)
        if args.agent not in KEYLESS_AGENTS and proxy is None:
            doctor.require_model_key(args.model)
    if arch.is_emulated(task.arch):
        logger.warning(arch.emulation_warning(task.arch))

    # Refuse a taken ID before the proxy starts or anything is built.
    run_id = getattr(args, "run_id", None) or new_run_id()
    taken = run_dir(task.name, args.agent, NO_MODEL if reference_run else str(args.model), run_id)
    if taken.exists():
        logger.error(f"{taken} already has results; give the run another --run-id, or none to get a new ID")
        return 1

    if proxy is None:
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
    model = NoModel() if reference_run or args.model is None else Model(args.model, proxy)
    timeout = args.timeout
    difficulty = args.difficulty
    keep_container = args.keep_container
    runner: BenchmarkSandboxRunner | BenchmarkSidecarRunner
    match args.mode:
        case "sandbox":
            runner = BenchmarkSandboxRunner(
                model,
                agent,
                task,
                timeout,
                difficulty,
                keep_container,
                tool_layer,
                egress,
                plugins=plugin_names,
                select_plugins=requested is not None,
                run_id=run_id,
                backend=backend,
                prebuilt=prebuilt,
            )
        case "sidecar":
            runner = BenchmarkSidecarRunner(
                model,
                agent,
                task,
                timeout,
                difficulty,
                keep_container,
                egress,
                run_id=run_id,
                backend=backend,
                prebuilt=prebuilt,
            )
        case _:
            logger.error(f"Unknown mode: {args.mode}")
            return 1
    try:
        runner.build()
    except CatalogError as e:
        logger.error(e)
        return 1
    # SIGTERM or SIGINT stops the container; the results are still recorded.
    with RunGuard():
        outcome = runner.run()
    report_outcome(outcome)
    return 1 if getattr(args, "require_pass", False) and not outcome.passed else 0


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
                stack.down(volumes=args.volumes)
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
    if args.benchmarks:
        benchmarks_dir = Path(args.benchmarks).resolve()
    else:
        _ = paths.require_checkout("The pilot task folders")
        benchmarks_dir = paths.default_dataset_dir()
    tasks = get_tasks(benchmarks_dir, args.tasks)

    if not tasks:
        logger.error("No tasks found")
        return 1

    logger.info(f"Found {len(tasks)} tasks to build")
    emulated: set[arch.Arch] = {task.arch for task in tasks if arch.is_emulated(task.arch)}
    for target in sorted(emulated):
        logger.warning(arch.emulation_warning(target))

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


def build_parser(commands: Sequence[Command] = ()) -> tuple[argparse.ArgumentParser, dict[str, Command]]:
    """Build the `ssebench` parser with the built-in commands and those of `commands` that configure.

    Returns the parser and the extension commands it includes, by name. The reference page
    docs/reference/cli.md is generated from this parser, so the help texts are also documentation.
    """
    parser = argparse.ArgumentParser(
        prog="ssebench",
        description="SSEBench CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"ssebench {VERSION}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ==================== run subcommand ====================
    run_parser = subparsers.add_parser(
        "run",
        help="Run a benchmark",
        description="Runs one agent on one task with one model and writes the results to "
        "results/TASK/MODEL/AGENT/RUN-ID/, a directory of its own for each run. "
        "SIGTERM or SIGINT stops the run's container, and the results and the summary are still written; "
        "a second signal ends the command at once.",
    )
    run_parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="NAME",
        help=f"Model name, as defined in models/*.yaml; required for every agent but {REFERENCE_AGENT}, which uses none",
    )
    run_parser.add_argument("--agent", required=True, metavar="NAME", help="Agent name, a directory under agents/")
    run_parser.add_argument("--task", required=True, metavar="ID", help="Task ID, the name of the task's folder")
    run_parser.add_argument(
        "--local",
        type=str,
        default="",
        metavar="DIR",
        help="Dataset directory that contains the task folder, for example datasets/pilot; "
        "the case image is built from the folder",
    )
    run_parser.add_argument(
        "--catalog",
        type=str,
        default="",
        metavar="PATH|URL",
        help=f"{tasks.CATALOG_HELP}; used when --local is not given",
    )
    run_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the task's case image from its folder instead of pulling the published one; needs a checkout "
        "or --catalog with the task folder next to it. With --local the image is always built",
    )
    run_parser.add_argument(
        "--mode",
        choices=["sandbox", "sidecar"],
        default="sandbox",
        metavar="MODE",
        help="Execution mode: sandbox, or sidecar (experimental)",
    )
    run_parser.add_argument(
        "--backend",
        type=str,
        default=None,
        metavar="NAME",
        help=f"Where the run's containers execute: docker or kubernetes (default: {DEFAULT_BACKEND}, or "
        "$SSEBENCH_BACKEND); installed extensions can add more. kubernetes needs --prebuilt",
    )
    run_parser.add_argument(
        "--prebuilt",
        action="store_true",
        help="Use the published agent images of the task under $SSEBENCH_REGISTRY, pulling them, instead of "
        "building the case, tool and agent layers; excludes --tool-layer, --plugin and --build. "
        "Also enabled by SSEBENCH_PREBUILT=1",
    )
    run_parser.add_argument(
        "--tool-layer",
        type=str,
        default=None,
        metavar="NAME",
        help=f"Tool layer to build in sandbox mode (default: {DEFAULT_TOOL_LAYER}); installed extensions can add more",
    )
    run_parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="NAME",
        help="Run a plugin in this run (repeatable), instead of those plugins.yaml enables; sandbox mode only",
    )
    run_parser.add_argument(
        "--run-id",
        type=run_id_arg,
        default=None,
        metavar="ID",
        help="Name the run: its directory is results/TASK/MODEL/AGENT/ID, and its containers get the label "
        f"`{RUN_ID_LABEL}=ID`, so a tool that starts the run can find them. 1 to 64 letters, digits, '.', '_' or '-', "
        "and not `latest`. The run is refused if that directory exists. "
        "Default: the UTC time the command started and six random hex digits, such as 20260929-153012-a1b2c3",
    )
    run_parser.add_argument(
        "--require-pass",
        action="store_true",
        help="Exit with status 1 unless the run's grade is passed, which needs every check the task has to pass; "
        "without it the command exits 0 whatever the grade. The grade is printed either way",
    )
    run_parser.add_argument("--timeout", type=int, default=3600, metavar="SECONDS", help="How long the agent may run")
    run_parser.add_argument(
        "--difficulty",
        type=int,
        choices=range(5),
        default=2,
        metavar="LEVEL",
        help="Which checks the agent's test_patch tool may run, from 0 (all) to 4 (none) (default: 2 = NO_FUTURE_TEST)",
    )
    run_parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep the container after the run, for example to inspect it from the web UI",
    )
    run_parser.add_argument(
        "--egress",
        choices=EGRESS_POLICIES,
        default=None,
        metavar="POLICY",
        help=(
            "Network egress of the run container: restricted reaches the LiteLLM proxy but not the internet; "
            "open also has internet access, for tasks that need network at test time "
            f"(default: ${EGRESS_ENV}, else restricted)"
        ),
    )

    # ==================== build-case subcommand ====================
    build_case_parser = subparsers.add_parser(
        "build-case",
        help="Build case images",
        description="Builds the case images of a dataset without running anything.",
    )
    build_case_parser.add_argument(
        "--benchmarks",
        type=str,
        default=None,
        metavar="DIR",
        help="Dataset directory (default: datasets/pilot in the SSEBench home)",
    )
    build_case_parser.add_argument(
        "--tasks",
        type=str,
        default=None,
        metavar="IDS",
        help="Comma-separated task IDs (default: every task)",
    )
    build_case_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild images even when they are up to date; without it, an image is rebuilt only when the "
        "task's files changed since it was built",
    )

    # ==================== dataset subcommand ====================
    dataset.add_parser(subparsers)

    # ==================== tasks subcommand ====================
    tasks.add_parser(subparsers)

    # ==================== runs subcommand ====================
    runs.add_parser(subparsers)

    # ==================== proxy subcommand ====================
    proxy_parser = subparsers.add_parser(
        "proxy",
        help="Start, rebuild or stop the local LiteLLM proxy",
        description="`up` rebuilds the proxy image first when models/ changed; `down` keeps the database volume "
        "unless you pass --volumes.",
    )
    proxy_parser.add_argument(
        "action",
        choices=["up", "build", "down"],
        metavar="ACTION",
        help="up: build the proxy image if it is missing or older than models/, start the stack and wait until "
        "the proxy is healthy; build: only build the image, if it is missing or older than models/; down: stop "
        "the stack and keep its database volume",
    )
    proxy_parser.add_argument(
        "--volumes",
        action="store_true",
        help="With down, also remove the database volume: the next start creates a new database with the "
        "POSTGRES_PASSWORD of .env, and the proxy's stored keys and spend records are gone",
    )
    proxy_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="With up or build, rebuild the proxy image even if it is current",
    )

    # ==================== init subcommand ====================
    init.add_parser(subparsers)

    # ==================== demo subcommand ====================
    demo.add_parser(subparsers)

    # ==================== doctor subcommand ====================
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check that this host can build and run benchmarks",
        description="Checks Docker, buildx, Compose, free disk, the CPU architecture, .env, "
        "the LiteLLM proxy and the provider keys. Exits non-zero when a required check fails.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the checks as JSON, with the provider keys that each model in models/ needs and .env lacks",
    )
    doctor_parser.add_argument(
        "--verify-keys",
        action="store_true",
        help="Also send each provider key in .env to its provider's model-list endpoint, which is not billed, "
        "to see whether the provider accepts it; needs internet access",
    )

    extensions: dict[str, Command] = {}
    for command in commands:
        try:
            # argparse cannot remove a subcommand once added, so try the arguments on a scratch parser first.
            command.configure(argparse.ArgumentParser())
        except Exception as e:
            logger.warning(f"Ignoring command {command.name!r}: configure() failed: {e}")
            continue
        command.configure(subparsers.add_parser(command.name, help=command.help, description=command.help))
        extensions[command.name] = command
    return parser, extensions


def main(argv: Sequence[str] | None = None):
    argv = sys.argv[1:] if argv is None else list(argv)
    # The `ssebench` console script enters here, not through __main__; without a handler the
    # progress messages would be dropped. A no-op when logging is already configured.
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser, extensions = build_parser(requested_extensions(argv))

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
        elif args.command in ("dataset", "tasks", "runs", "init", "demo"):
            sys.exit(args.handler(args))
        elif args.command == "proxy":
            sys.exit(cmd_proxy(args))
        elif args.command == "doctor":
            sys.exit(doctor.main(as_json=args.json, verify_keys=args.verify_keys))
        elif args.command in extensions:
            sys.exit(extensions[args.command].run(args))
        else:
            parser.print_help()
            sys.exit(1)
    except (paths.HomeNotFoundError, settings.SettingError, UserError) as e:
        logger.error(e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.error("Interrupted")
        sys.exit(130)
