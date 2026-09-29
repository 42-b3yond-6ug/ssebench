"""An SSEBench extension that adds the `example` tool layer and the `hello` command."""

import argparse
import subprocess
from typing import override

from ssebench.extensions import REGISTRY, Command, SandboxToolLayer, ToolLayer

# Builds on the standard runtime rather than replacing it: the agent layer and the
# entrypoint still need the daemon, the MCP server and the evaluator it installs.
DOCKERFILE = """\
FROM runtime
LABEL org.example.tool-layer="example"
"""


class ExampleToolLayer(ToolLayer):
    """The built-in sandbox runtime with one more image layer on top."""

    @override
    def docker_image(self, base: str | None) -> str:
        runtime = SandboxToolLayer(self.context).docker_image(base)
        image = f"{REGISTRY}/tool-example/{self.context.task_name.lower()}"
        _ = subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--build-context",
                f"runtime=docker-image://{runtime}",
                "-t",
                image,
                "--load",
                "-",
            ],
            input=DOCKERFILE,
            text=True,
            check=True,
        )
        return image


class HelloCommand(Command):
    name = "hello"
    help = "Print a greeting"

    @override
    def configure(self, parser: argparse.ArgumentParser) -> None:
        _ = parser.add_argument("--name", default="world", help="Who to greet")

    @override
    def run(self, args: argparse.Namespace) -> int:
        print(f"Hello, {args.name}!")
        return 0
