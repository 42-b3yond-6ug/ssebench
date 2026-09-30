"""The container layout of a sidecar run: what each container gets, and what the agent never does."""

import logging
from pathlib import Path

import pytest

from ssebench import stack
from ssebench.backends import (
    ARCHIVE_PATH,
    RESULTS_PATH,
    SIDECAR_DAEMON_SOCKET,
    SIDECAR_SOCKET_DIR,
    DockerBackend,
    Mount,
    NetworkPolicy,
    RunSpec,
    SidecarPair,
)
from ssebench.cli.cli import main

PILOT = Path(__file__).resolve().parents[2] / "datasets" / "pilot"
TASK = "gjson-196-bf4efcb"


def make_spec(**kw: object) -> RunSpec:
    pair = SidecarPair(
        task_name="Demo-1",
        source_dir="/src/demo",
        environment_image="registry.test/environment",
        difficulty=4,
        run_id="abc123",
    )
    fields: dict[str, object] = {
        "run_id": "r1",
        "mode": "sidecar",
        "task_name": "Demo-1",
        "image": "registry.test/agent",
        "env": {},
        "results": Mount(source="/host/results", target=RESULTS_PATH),
        "archive": Mount(source="/host/results/archive", target=ARCHIVE_PATH),
        "network": NetworkPolicy(),
        "labels": {},
        "timeout": 60,
        "sidecar": pair,
    }
    return RunSpec(**{**fields, **kw})  # pyright: ignore[reportArgumentType]


BACKEND = DockerBackend(network="ssebench_agents")


def both(spec: RunSpec) -> tuple[list[str], list[str]]:
    return BACKEND.environment_options(spec), BACKEND.agent_options(spec)


def pairs(options: list[str], flag: str) -> list[str]:
    return [options[i + 1] for i, option in enumerate(options) if option == flag]


def test_both_containers_share_the_source_sockets_and_archive() -> None:
    for options in both(make_spec()):
        assert pairs(options, "-v") == [
            f"/host/results/archive:{ARCHIVE_PATH}",
            "ssebench-abc123-source:/src/demo",
            f"ssebench-abc123-sockets:{SIDECAR_SOCKET_DIR}",
            f"/host/results:{RESULTS_PATH}",
        ]
        assert f"SSE_RESULTS={RESULTS_PATH}" in pairs(options, "-e")


def test_the_agent_container_never_mounts_the_task_files() -> None:
    options = BACKEND.agent_options(make_spec(env={"SSE_API_KEY": "sk-x"}))

    targets = [volume.split(":")[1] for volume in pairs(options, "-v")]
    assert not any(target == "/ssebench" or target.startswith("/ssebench/") for target in targets)
    assert "/ssebench-repo" not in targets
    assert not [volume for volume in pairs(options, "-v") if volume.endswith(":/sse_result")]
    assert "SSE_API_KEY=sk-x" in pairs(options, "-e")


def test_the_sockets_are_off_the_writable_archive() -> None:
    assert not SIDECAR_DAEMON_SOCKET.startswith(ARCHIVE_PATH)
    for options in both(make_spec()):
        assert f"SSE_DAEMON_SOCKET={SIDECAR_DAEMON_SOCKET}" in pairs(options, "-e")


def test_the_daemon_gets_the_difficulty_and_the_network() -> None:
    for options in both(make_spec()):
        assert "SSE_DIFFICULTY=4" in pairs(options, "-e")
        assert pairs(options, "--network") == ["ssebench_agents"]
        assert "ssebench.run=abc123" in pairs(options, "--label")


def test_the_environment_container_alone_keeps_the_task_alive_and_carries_the_labels() -> None:
    spec = make_spec(labels={"ssebench.webui": "true"})
    environment, agent = both(spec)

    assert "SSE_KEEP_ALIVE=0" in pairs(environment, "-e") and "SSE_KEEP_ALIVE=0" not in pairs(agent, "-e")
    assert "ssebench.webui=true" in pairs(environment, "--label")
    assert "ssebench.webui=true" not in pairs(agent, "--label")
    assert pairs(environment, "--name") == ["ssebench-env-demo-1-abc123"] and not pairs(agent, "--name")


def test_each_run_has_its_own_names() -> None:
    first = SidecarPair(task_name="Demo-1", source_dir="/s", environment_image="e", difficulty=2, run_id="one")
    second = SidecarPair(task_name="Demo-1", source_dir="/s", environment_image="e", difficulty=2, run_id="two")

    assert first.environment_name == "ssebench-env-demo-1-one"
    assert {*first.volumes}.isdisjoint({*second.volumes})
    assert len(SidecarPair(task_name="t", source_dir="/s", environment_image="e", difficulty=2).run_id) == 12


def test_run_warns_that_sidecar_mode_is_experimental(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def stop(*_: object, **__: object) -> None:
        raise TimeoutError("stopped before the proxy starts")

    monkeypatch.setattr(stack, "up", stop)
    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit) as exit_info:
        main(["run", "--model", "m", "--agent", "dummy", "--task", TASK, "--local", str(PILOT), "--mode", "sidecar"])

    assert exit_info.value.code == 1
    assert "Sidecar mode is experimental" in caplog.text
