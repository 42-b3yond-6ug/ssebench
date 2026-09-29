"""Extensions installed from another package work without changes to SSEBench.

The example extension in fixtures/ssebench_example_ext is installed the way an installer lays it
out: its package on sys.path and a dist-info with its entry points in a site directory.
"""

import logging
import os
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast, override

import pytest

from ssebench.agents import Agent
from ssebench.cli.cli import main, requested_extensions
from ssebench.extensions import (
    ExtensionError,
    SandboxToolLayer,
    ToolLayer,
    command_names,
    get_tool_layer,
    load_commands,
    tool_layer_names,
)
from ssebench.models import Model
from ssebench.pipe import DockerLayerMixin
from ssebench.runner import BenchmarkSandboxRunner
from ssebench.runner import runner as runner_module
from ssebench.tasks import Task
from ssebench.tasks.metadata import Files, TaskDescription, TaskMetadata

EXAMPLE = Path(__file__).parent / "fixtures" / "ssebench_example_ext"
EXAMPLE_MODULE = "ssebench_example_ext"

# Test-only modules for the failure cases, so the example stays a clean example.
BROKEN_MODULE = """
import argparse


class FailingConfigure:
    name = "failing"
    help = "configure() raises"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        raise RuntimeError("bad arguments")

    def run(self, args: argparse.Namespace) -> int:
        return 0


class NotACommand:
    pass
"""


def install(site: Path, name: str, entry_points: Mapping[str, Mapping[str, str]], version: str = "1.0") -> None:
    """Write the dist-info an installer would write for a distribution with these entry points."""
    dist_info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    dist_info.mkdir()
    _ = (dist_info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    sections = [
        "\n".join([f"[{group}]", *(f"{key} = {value}" for key, value in points.items())])
        for group, points in entry_points.items()
    ]
    _ = (dist_info / "entry_points.txt").write_text("\n\n".join(sections) + "\n")


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """An empty site directory at the front of sys.path."""
    site = tmp_path / "site"
    site.mkdir()
    _ = (site / "broken_ext.py").write_text(BROKEN_MODULE)
    monkeypatch.syspath_prepend(str(site))
    yield site
    for module in (EXAMPLE_MODULE, "broken_ext"):
        _ = sys.modules.pop(module, None)


@pytest.fixture
def example(site: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install the example extension from its pyproject.toml."""
    project = tomllib.loads((EXAMPLE / "pyproject.toml").read_text())["project"]
    install(site, project["name"], project["entry-points"], project["version"])
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    return site


# ==================== tool layers ====================


def test_builtin_tool_layer() -> None:
    assert get_tool_layer("sandbox") is SandboxToolLayer


def test_example_tool_layer_is_selectable(example: Path) -> None:
    assert tool_layer_names() == ["example", "sandbox"]

    layer = get_tool_layer("example")

    assert issubclass(layer, ToolLayer)
    assert layer.__module__ == EXAMPLE_MODULE


def test_unknown_tool_layer() -> None:
    with pytest.raises(ExtensionError, match=r"Unknown tool layer 'nope'\. Available: .*sandbox"):
        _ = get_tool_layer("nope")


def test_tool_layer_cannot_shadow_a_builtin(example: Path) -> None:
    install(example, "shadow", {"ssebench.tool_layers": {"sandbox": f"{EXAMPLE_MODULE}:ExampleToolLayer"}})

    with pytest.raises(ExtensionError, match=r"'sandbox' is registered more than once: the built-in layer; .*shadow"):
        _ = get_tool_layer("sandbox")


def test_tool_layer_registered_twice(example: Path) -> None:
    install(example, "copycat", {"ssebench.tool_layers": {"example": f"{EXAMPLE_MODULE}:ExampleToolLayer"}})

    with pytest.raises(ExtensionError, match=r"'example' is registered more than once") as error:
        _ = get_tool_layer("example")
    assert "ssebench-example-ext" in str(error.value)
    assert "copycat" in str(error.value)


def test_tool_layer_must_be_a_tool_layer(example: Path) -> None:
    install(example, "wrong", {"ssebench.tool_layers": {"wrong": f"{EXAMPLE_MODULE}:HelloCommand"}})

    with pytest.raises(ExtensionError, match="not a subclass of ssebench.extensions.ToolLayer"):
        _ = get_tool_layer("wrong")


def test_tool_layer_that_fails_to_import(site: Path) -> None:
    install(site, "missing", {"ssebench.tool_layers": {"missing": "no_such_module:Layer"}})

    with pytest.raises(ExtensionError, match=r"Cannot load tool layer 'missing' \(no_such_module:Layer from missing\)"):
        _ = get_tool_layer("missing")


class FakeTask(Task):
    name = "generic-go-example-1"
    docker_image_name = "case-image"

    @override
    def docker_image(self, base: str | None) -> str:
        return self.docker_image_name

    @override
    def case_image_exists(self) -> bool:
        return True

    @override
    def get_task_metadata(self) -> TaskMetadata:
        return TaskMetadata(
            id=self.name,
            project="example",
            language="go",
            source="/src/example",
            task_description=TaskDescription(issue="An example issue"),
            scripts={},
            files=Files(),
        )


def test_sandbox_runner_builds_the_selected_layer(example: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipelines: list[list[DockerLayerMixin]] = []

    def record(pipeline: list[DockerLayerMixin]) -> str:
        pipelines.append(pipeline)
        return "image"

    monkeypatch.setattr(runner_module, "build_pipe", record)
    task = FakeTask()
    agent = Agent("dummy", task_name=task.name)
    runner = BenchmarkSandboxRunner(cast(Model, None), agent, task, 60, 2, tool_layer="example")

    runner.build()

    [[case, layer, agent_layer]] = pipelines
    assert case is task
    assert agent_layer is agent
    assert isinstance(layer, get_tool_layer("example"))
    assert layer.context.task_name == task.name
    assert layer.context.source_dir == "/src/example"


# ==================== commands ====================


def run_cli(*argv: str) -> int:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    return cast(int, exit_info.value.code)


def test_hello_command(example: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("hello", "--name", "SSEBench") == 0
    assert capsys.readouterr().out == "Hello, SSEBench!\n"


def test_help_lists_extension_commands(example: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("--help") == 0

    out = capsys.readouterr().out
    assert "hello" in out
    assert "Print a greeting" in out
    assert "build-case" in out


def test_broken_commands_do_not_break_the_cli(
    example: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    install(
        example,
        "broken",
        {
            "ssebench.commands": {
                "missing": "no_such_module:Command",
                "not-a-command": "broken_ext:NotACommand",
                "failing": "broken_ext:FailingConfigure",
                "run": f"{EXAMPLE_MODULE}:HelloCommand",
                "salute": f"{EXAMPLE_MODULE}:HelloCommand",
            }
        },
    )

    with caplog.at_level(logging.WARNING):
        assert run_cli("--help") == 0

    out = capsys.readouterr().out
    assert "hello" in out
    for name in ("missing", "not-a-command", "failing", "salute"):
        assert name not in out
    warnings = caplog.text
    assert "'missing'" in warnings and "cannot load it" in warnings
    assert "'not-a-command'" in warnings and "does not implement ssebench.extensions.Command" in warnings
    assert "'failing'" in warnings and "configure() failed: bad arguments" in warnings
    assert "'run'" in warnings and "a built-in command has that name" in warnings
    assert "'salute'" in warnings and "calls itself 'hello'" in warnings


def test_builtin_commands_import_no_extension(site: Path, caplog: pytest.LogCaptureFixture) -> None:
    install(site, "broken", {"ssebench.commands": {"missing": "no_such_module:Command"}})

    with caplog.at_level(logging.WARNING):
        assert requested_extensions(["build-case", "--tasks", "x"]) == []
    assert caplog.text == ""


def test_extension_command_imports_only_itself(example: Path, caplog: pytest.LogCaptureFixture) -> None:
    install(example, "broken", {"ssebench.commands": {"missing": "no_such_module:Command"}})

    assert command_names() == ["hello", "missing"]
    with caplog.at_level(logging.WARNING):
        assert [command.name for command in requested_extensions(["hello"])] == ["hello"]
    assert caplog.text == ""
    assert load_commands("missing") == []


def test_run_rejects_an_unknown_tool_layer(caplog: pytest.LogCaptureFixture) -> None:
    status = run_cli(
        "run", "--model", "m", "--agent", "dummy", "--task", "t", "--local", "datasets", "--tool-layer", "nope"
    )

    assert status == 1
    assert "Unknown tool layer 'nope'" in caplog.text


def test_run_rejects_a_tool_layer_in_sidecar_mode(caplog: pytest.LogCaptureFixture) -> None:
    status = run_cli(
        "run", "--model", "m", "--agent", "dummy", "--task", "t", "--local", "datasets", "--mode", "sidecar",
        "--tool-layer", "sandbox",
    )  # fmt: skip

    assert status == 1
    assert "--tool-layer applies to sandbox mode only" in caplog.text


def test_installed_extension_in_a_new_process(example: Path, tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(example), str(EXAMPLE / "src")])}

    def ssebench(*argv: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "ssebench", *argv], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
        )
        return result.stdout

    assert "Print a greeting" in ssebench("--help")
    assert "--tool-layer NAME" in ssebench("run", "--help")
    assert ssebench("hello") == "Hello, world!\n"
