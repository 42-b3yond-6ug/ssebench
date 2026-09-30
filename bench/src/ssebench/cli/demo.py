"""`ssebench demo`: the local demo, a Compose stack with the web UI and one kept run."""

import argparse
import logging
import subprocess
from collections.abc import Callable

from ssebench import demo
from ssebench.errors import UserError

logger = logging.getLogger(__name__)


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "demo",
        help="Start the local demo: the stack, one run and the web UI",
        description="Runs the LiteLLM proxy, the task catalog and the web UI in a Compose project of their own, "
        "and leaves one finished run in the web UI. Linux only.",
    )
    commands = parser.add_subparsers(dest="demo_command", metavar="COMMAND", required=True)

    up = commands.add_parser(
        "up",
        help="Start the demo stack, run one agent on one task and show the run in the web UI",
        description="Gets the images (pulls them, or builds what the registry lacks), starts the stack, runs the "
        "agent with --keep-container and prints the web UI's address. The reference agent needs no key; another "
        "agent needs its model's provider key in .env. Run it again to replace the run.",
    )
    _ = up.add_argument(
        "--task",
        default=demo.DEFAULT_TASK,
        metavar="ID",
        help="Task ID, from the bundled pilot dataset; pick a fast one (default: gjson-196-bf4efcb)",
    )
    _ = up.add_argument(
        "--agent",
        default=demo.DEFAULT_AGENT,
        metavar="NAME",
        help="Agent name, a directory under agents/; reference applies the task's known fix (default: reference)",
    )
    _ = up.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="Model name, as defined in models/*.yaml; required for every agent but reference",
    )
    _ = up.add_argument(
        "--timeout",
        type=int,
        default=demo.DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"How long the agent may run (default: {demo.DEFAULT_TIMEOUT})",
    )
    _ = up.add_argument(
        "--build",
        action="store_true",
        help="Build every image from this checkout instead of pulling the published ones",
    )
    up.set_defaults(handler=cmd_up)

    down = commands.add_parser(
        "down",
        help="Remove everything the demo created",
        description="Removes the demo's run containers, its Compose project and the project's database volume. "
        "Results, the cached images and every other container stay.",
    )
    down.set_defaults(handler=cmd_down)


def cmd_up(args: argparse.Namespace) -> int:
    plan = demo.Plan(task=args.task, agent=args.agent, model=args.model, timeout=args.timeout, build=args.build)
    return guarded(lambda: demo.up(plan))


def cmd_down(args: argparse.Namespace) -> int:
    return guarded(demo.down)


def guarded(action: Callable[[], int]) -> int:
    try:
        return action()
    except (demo.DemoError, UserError) as e:
        logger.error(e)
    except subprocess.CalledProcessError as e:
        logger.error(f"{' '.join(str(part) for part in e.cmd)} failed with exit code {e.returncode}")
    except (FileNotFoundError, TimeoutError) as e:
        logger.error(e)
    except KeyboardInterrupt:
        return 130
    return 1
