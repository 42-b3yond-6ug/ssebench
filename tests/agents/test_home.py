"""An agent starts with the home and the git identity of the user `model`.

The entrypoint starts the agent as `model` with `su -p`, which keeps root's environment. Without
a correction the agent has `HOME=/root`, which `model` cannot read, and `git commit` fails with
"Author identity unknown". The test runs a one-command agent in both modes of a real run of
gjson-196-bf4efcb and reads what it saw from `agent.log`. The agent makes no model call, so the
run needs no proxy and no key.

    make -C images/base-images generic-go
    uv run pytest tests/agents -m agents -k home

It needs Docker and the base image under SSEBENCH_REGISTRY, like the other tests in this folder.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

TASK = "gjson-196-bf4efcb"
SOURCE = "/src/gjson"

pytestmark = [
    pytest.mark.agents,
    pytest.mark.skipif(shutil.which("docker") is None, reason="needs Docker"),
]

CHECK = f"""\
#!/bin/sh
echo "user=$(id -un) uid=$(id -u)"
echo "home=$HOME"
echo "home-readable=$(test -r "$HOME" && test -w "$HOME" && echo yes || echo no)"
cd {SOURCE}
git commit --allow-empty -q -m "commit by the agent" && echo "committed=yes" || echo "committed=no"
echo "author=$(git log -1 --format='%an <%ae>')"
"""


@pytest.mark.parametrize("mode", ["sandbox", "sidecar"])
def test_the_agent_can_commit_as_model_from_its_home(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssebench import paths, stack
    from ssebench.agents import Agent
    from ssebench.models import NoModel
    from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
    from ssebench.tasks import LocalTask

    agents = tmp_path / "agents"
    (agents / "homecheck").mkdir(parents=True)
    _ = (agents / "homecheck" / "agent.yaml").write_text("name: homecheck\n")
    _ = (agents / "homecheck" / "check.sh").write_text(CHECK)
    _ = (agents / "homecheck" / "Dockerfile").write_text(
        'FROM ssebench-agent\nCOPY --chmod=755 check.sh /usr/local/bin/homecheck\nCMD ["homecheck"]\n'
    )
    monkeypatch.setattr(paths, "agents_dir", lambda: agents)
    # The agent needs no network: the daemon, the MCP server and the evaluator talk over the
    # container's loopback and a Unix socket.
    monkeypatch.setattr(stack, "run_network", lambda egress: "none")

    task = LocalTask(TASK, paths.default_dataset_dir())
    agent = Agent("homecheck", task_name=task.name)
    runner_class = BenchmarkSandboxRunner if mode == "sandbox" else BenchmarkSidecarRunner
    runner = runner_class(NoModel(), agent, task, 300, 2)
    runner.build()

    monkeypatch.chdir(tmp_path)
    runner.run()

    log = (tmp_path / "results" / TASK / "none" / "homecheck" / "agent.log").read_text()
    seen = log.splitlines()
    for line in (
        "user=model uid=1000",
        "home=/home/model",
        "home-readable=yes",
        "committed=yes",
        "author=SSEBench Agent <agent@ssebench.invalid>",
    ):
        assert line in seen, log
