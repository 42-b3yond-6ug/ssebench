"""Every bundled agent starts, calls the model and exits cleanly without internet.

Each test builds the images of one agent for gjson-196-bf4efcb and runs it with the
runner of `ssebench run`, on a new internal Docker network: no internet, no DNS for
outside names. The network's only other member is `stub_llm.py`, reachable as
`litellm:4000`, where the LiteLLM proxy would be; it answers every model call with
"I'm done.". A test passes when the agent container exits with status 0, the agent
made at least one model call (except `dummy`, which makes none), its wrapper
reports a clean finish, and the evaluator wrote a grade.

Sandbox mode covers every agent; sidecar mode every agent that supports it
(OpenCode does not).

    make -C images/base-images generic-go
    uv run pytest tests/agents -m agents                  # all agents, both modes
    uv run pytest tests/agents -m agents -k "codex and sidecar"

It needs Docker, the base image under SSEBENCH_REGISTRY, and network access to
build the images and pull the stub's Python image; only the runs are offline.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

TASK = "gjson-196-bf4efcb"
STUB = Path(__file__).with_name("stub_llm.py")
STUB_IMAGE = "python:3.12-alpine"
# Long enough for any agent to start; a wrapper that waits on the internet times out.
AGENT_TIMEOUT = 300

pytestmark = [
    pytest.mark.agents,
    pytest.mark.skipif(shutil.which("docker") is None, reason="needs Docker"),
]


@dataclass(frozen=True)
class StubModel:
    """Stands in for `ssebench.models.Model`: the stub needs no key and costs nothing."""

    model_name: str
    api_key: str = "sk-offline-test"
    service_url: str = "http://litellm:4000"

    def get_spend(self) -> float:
        return 0.0


def last_dialog_entry(run: Path) -> dict[str, object]:
    lines = (run / "dialog.jsonl").read_text().splitlines()
    return json.loads(lines[-1])


@dataclass(frozen=True)
class Case:
    agent: str
    model: str
    finished: Callable[[Path], bool]
    """Whether the wrapper reports a clean finish, from the run directory."""
    calls_model: bool = True
    sidecar: bool = True


CASES = [
    Case("dummy", "claude-sonnet-4-6", lambda run: "dummy_QAQ" in (run / "agent.log").read_text(), calls_model=False),
    Case(
        "claude-code",
        "claude-sonnet-4-6",
        lambda run: (
            "[claude] exited with code 0" in (run / "agent.log").read_text()
            and last_dialog_entry(run).get("status") == "success"
        ),
    ),
    Case("codex", "gpt-5.1-codex", lambda run: "[codex] exited with code 0" in (run / "agent.log").read_text()),
    Case(
        "opencode",
        "gpt-5.1",
        lambda run: (
            last_dialog_entry(run).get("type") == "complete" and last_dialog_entry(run).get("status") == "success"
        ),
        sidecar=False,
    ),
]
PARAMS = [
    pytest.param(case, mode, id=f"{case.agent}-{mode}")
    for case in CASES
    for mode in ("sandbox", "sidecar")
    if mode == "sandbox" or case.sidecar
]


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def offline_network() -> Iterator[tuple[str, Callable[[], list[dict[str, object]]]]]:
    """An internal network with the stub proxy on it, and a function that returns its requests."""
    name = f"ssebench-offline-{uuid.uuid4().hex[:8]}"
    _ = docker("network", "create", "--internal", name)
    stub = f"{name}-stub"
    try:
        _ = docker(
            "run",
            "--detach",
            "--name",
            stub,
            "--network",
            name,
            "--network-alias",
            "litellm",
            "-v",
            f"{STUB}:/stub_llm.py:ro",
            STUB_IMAGE,
            "python",
            "-u",
            "/stub_llm.py",
            "4000",
        )

        def requests() -> list[dict[str, object]]:
            logs = docker("logs", stub)
            return [r for r in map(json.loads, logs.splitlines()) if "method" in r]

        yield name, requests
    finally:
        subprocess.run(["docker", "rm", "--force", stub], capture_output=True)
        subprocess.run(["docker", "network", "rm", name], capture_output=True)


@pytest.mark.parametrize(("case", "mode"), PARAMS)
def test_agent_runs_offline(
    case: Case,
    mode: str,
    offline_network: tuple[str, Callable[[], list[dict[str, object]]]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ssebench import paths, stack
    from ssebench.agents import Agent
    from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
    from ssebench.tasks import LocalTask

    network, model_requests = offline_network
    monkeypatch.setattr(stack, "run_network", lambda egress: network)
    task = LocalTask(TASK, paths.default_dataset_dir())
    model = StubModel(case.model)
    agent = Agent(case.agent, task_name=task.name)
    runner_class = BenchmarkSandboxRunner if mode == "sandbox" else BenchmarkSidecarRunner
    runner = runner_class(model, agent, task, AGENT_TIMEOUT, 2)  # pyright: ignore[reportArgumentType]
    runner.build()

    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.WARNING, logger="ssebench.runner.runner"):
        runner.run()

    run = tmp_path / "results" / TASK / case.model / case.agent
    requests = model_requests()
    calls = [r for r in requests if r["method"] == "POST"]
    report = f"stub requests: {requests}\nagent.log:\n{(run / 'agent.log').read_text()[-3000:]}"
    print(f"{case.agent} ({mode}): model calls {[(r['method'], r['path']) for r in calls]}")

    assert "failed" not in caplog.text and "non-zero" not in caplog.text, f"{caplog.text}\n{report}"
    assert case.finished(run), report
    if case.calls_model:
        assert calls, report
    else:
        assert not calls, report
    grade = json.loads((run / "result.json").read_text())
    assert grade["patch_result"]["build_success"] is True, report
