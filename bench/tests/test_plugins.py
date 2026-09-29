"""Loading, validating and selecting plugins from plugins.yaml."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

import pytest

from ssebench.agents import Agent
from ssebench.middleware import ToolLayer
from ssebench.models import Model
from ssebench.plugins import (
    Plugin,
    PluginError,
    load_plugins,
    select_plugins,
    selected_plugins,
)
from ssebench.runner import BenchmarkSandboxRunner
from ssebench.runner import runner as runner_module

from .test_extensions import FakeTask

# The schema the CLI ships; the tests validate against the real one.
SCHEMA = json.loads((Path(__file__).parents[2] / "runtime" / "plugins" / "schema.json").read_text())


def write_plugins(directory: Path, yaml_text: str) -> None:
    (directory / "schema.json").write_text(json.dumps(SCHEMA))
    (directory / "plugins.yaml").write_text(yaml_text)


def make_run_sh(directory: Path, name: str) -> None:
    pdir = directory / name
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "run.sh").write_text("#!/bin/sh\ntrue\n")


def test_missing_file_means_no_plugins(tmp_path: Path):
    assert load_plugins(tmp_path) == []


def test_valid_file_loads(tmp_path: Path):
    write_plugins(
        tmp_path,
        """
- name: artifact
  enabled: true
  hook: after-grading
  llm: false
  timeout: 5
""",
    )
    plugins = load_plugins(tmp_path)
    assert plugins == [Plugin(name="artifact", enabled=True, hook="after-grading", llm=False, timeout=5)]


@pytest.mark.parametrize(
    "yaml_text",
    [
        "- {name: x, enabled: true, hook: during:agent, llm: false, timeout: 5}",  # bad hook
        "- {name: x, enabled: true, hook: on-agent, llm: false, timeout: 5, extra: 1}",  # extra field
        "- {name: x, enabled: true, hook: on-agent, llm: false}",  # missing field
        "- {name: Bad_Name, enabled: true, hook: on-agent, llm: false, timeout: 5}",  # bad name
        "- {name: x, enabled: true, hook: on-agent, llm: false, timeout: 0}",  # zero timeout
    ],
)
def test_schema_rejects_bad_files(tmp_path: Path, yaml_text: str):
    write_plugins(tmp_path, yaml_text)
    with pytest.raises(PluginError):
        load_plugins(tmp_path)


def test_duplicate_name_rejected(tmp_path: Path):
    write_plugins(
        tmp_path,
        """
- {name: dup, enabled: true, hook: on-agent, llm: false, timeout: 5}
- {name: dup, enabled: false, hook: after-grading, llm: false, timeout: 5}
""",
    )
    with pytest.raises(PluginError, match="declared twice"):
        load_plugins(tmp_path)


def test_select_by_enabled_field():
    plugins = [
        Plugin("artifact", True, "after-grading", False, 5),
        Plugin("oracle", False, "after-grading", True, 60),
    ]
    selected, unknown = select_plugins(plugins, None)
    assert [p.name for p in selected] == ["artifact"]
    assert unknown == []


def test_request_overrides_enabled_and_reports_unknown():
    plugins = [
        Plugin("artifact", True, "after-grading", False, 5),
        Plugin("oracle", False, "after-grading", True, 60),
    ]
    selected, unknown = select_plugins(plugins, ["oracle", "ghost"])
    assert [p.name for p in selected] == ["oracle"]
    assert unknown == ["ghost"]


def test_selected_plugins_checks_run_sh(tmp_path: Path):
    write_plugins(
        tmp_path,
        """
- {name: artifact, enabled: true, hook: after-grading, llm: false, timeout: 5}
""",
    )
    # No run.sh yet: selecting it fails.
    with pytest.raises(PluginError, match="run.sh"):
        selected_plugins(None, directory=tmp_path)

    make_run_sh(tmp_path, "artifact")
    assert [p.name for p in selected_plugins(None, directory=tmp_path)] == ["artifact"]

    # A requested plugin that is not declared is an error.
    with pytest.raises(PluginError, match="unknown plugin"):
        selected_plugins(["ghost"], directory=tmp_path)


def test_sandbox_runner_installs_selected_plugins(monkeypatch: pytest.MonkeyPatch):
    """--plugin reaches the tool layer (to install) and is recorded on the run."""
    built: list[ToolLayer] = []

    def record(pipeline: list[object]) -> str:
        built.append(cast(ToolLayer, pipeline[1]))
        return "image"

    monkeypatch.setattr(runner_module, "build_pipe", record)
    task = FakeTask()
    agent = Agent("dummy", task_name=task.name)
    runner = BenchmarkSandboxRunner(cast(Model, None), agent, task, 60, 2, plugins=["artifact"], select_plugins=True)
    runner.build()

    assert built[0].context.plugins == ("artifact",)
    assert runner.plugins == ["artifact"]
    assert runner.select_plugins is True


def _run_args(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "model": "m",
        "agent": "dummy",
        "task": "t",
        "local": "",
        "catalog": "",
        "mode": "sandbox",
        "tool_layer": None,
        "plugin": [],
        "timeout": 60,
        "difficulty": 2,
        "keep_container": False,
        "egress": "restricted",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cmd_run_rejects_plugin_in_sidecar_mode():
    from ssebench.cli.cli import cmd_run

    # Returns before touching Docker or the proxy.
    assert cmd_run(_run_args(mode="sidecar", plugin=["artifact"])) == 1


def test_cmd_run_rejects_unknown_plugin():
    from ssebench.cli.cli import cmd_run

    assert cmd_run(_run_args(plugin=["definitely-not-a-plugin"])) == 1


def test_oracle_skips_without_llm(tmp_path: Path):
    """Without SSE_* the oracle exits 0 without touching grading or importing
    the container-only SDK modules."""
    import os
    import subprocess
    import sys

    oracle_main = Path(__file__).parents[2] / "runtime" / "plugins" / "oracle" / "main.py"
    env = {k: v for k, v in os.environ.items() if k not in ("SSE_API_KEY", "SSE_BASE_URL", "SSE_MODEL_NAME")}
    env["SSE_ARCHIVE"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(oracle_main)],
        env=env,
        capture_output=True,
        text=True,
        cwd=oracle_main.parent,
    )
    assert result.returncode == 0, result.stderr
    assert "skipping" in result.stderr.lower() or "skipping" in result.stdout.lower()
    # It wrote nothing into the results directory.
    assert list(tmp_path.iterdir()) == []


def test_shipped_plugins_yaml_is_valid():
    """The plugins.yaml in the repository loads and its plugins have run.sh."""
    plugins = load_plugins()
    names = {p.name for p in plugins}
    assert {"artifact", "oracle"} <= names
    for p in plugins:
        assert (Path(__file__).parents[2] / "runtime" / "plugins" / p.name / "run.sh").is_file()
