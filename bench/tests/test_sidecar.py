"""The container layout of a sidecar run: what each container gets, and what the agent never does."""

import logging
from pathlib import Path

import pytest

from ssebench import stack
from ssebench.cli.cli import main
from ssebench.runner import SidecarPair
from ssebench.runner.runner import ARCHIVE_PATH, RESULTS_PATH, SIDECAR_DAEMON_SOCKET, SIDECAR_SOCKET_DIR

PILOT = Path(__file__).resolve().parents[2] / "datasets" / "pilot"
TASK = "gjson-196-bf4efcb"


def make_pair(**kw: object) -> SidecarPair:
    fields: dict[str, object] = {
        "task_name": "Demo-1",
        "source_dir": "/src/demo",
        "results": "/host/results",
        "archive": "/host/results/archive",
        "network": "ssebench_agents",
        "difficulty": 4,
        "run_id": "abc123",
    }
    return SidecarPair(**{**fields, **kw})  # pyright: ignore[reportArgumentType]


def pairs(options: list[str], flag: str) -> list[str]:
    return [options[i + 1] for i, option in enumerate(options) if option == flag]


def test_both_containers_share_the_source_sockets_and_archive() -> None:
    pair = make_pair()
    for options in (pair.environment_options(), pair.agent_options()):
        assert pairs(options, "-v")[:4] == [
            f"/host/results/archive:{ARCHIVE_PATH}",
            "ssebench-abc123-source:/src/demo",
            f"ssebench-abc123-sockets:{SIDECAR_SOCKET_DIR}",
            f"/host/results:{RESULTS_PATH}",
        ]
        assert f"SSE_RESULTS={RESULTS_PATH}" in pairs(options, "-e")


def test_the_agent_container_never_mounts_the_task_files() -> None:
    options = make_pair().agent_options({"SSE_API_KEY": "sk-x"})

    targets = [volume.split(":")[1] for volume in pairs(options, "-v")]
    assert not any(target == "/ssebench" or target.startswith("/ssebench/") for target in targets)
    assert "/ssebench-repo" not in targets
    assert not [volume for volume in pairs(options, "-v") if volume.endswith(":/sse_result")]
    assert "SSE_API_KEY=sk-x" in pairs(options, "-e")


def test_the_sockets_are_off_the_writable_archive() -> None:
    assert not SIDECAR_DAEMON_SOCKET.startswith(ARCHIVE_PATH)
    for options in (make_pair().environment_options(), make_pair().agent_options()):
        assert f"SSE_DAEMON_SOCKET={SIDECAR_DAEMON_SOCKET}" in pairs(options, "-e")


def test_the_daemon_gets_the_difficulty_and_the_network() -> None:
    pair = make_pair(difficulty=4, network="ssebench_agents")
    for options in (pair.environment_options(), pair.agent_options()):
        assert "SSE_DIFFICULTY=4" in pairs(options, "-e")
        assert pairs(options, "--network") == ["ssebench_agents"]
        assert "ssebench.run=abc123" in pairs(options, "--label")


def test_each_run_has_its_own_names() -> None:
    first, second = make_pair(run_id="one"), make_pair(run_id="two")

    assert first.environment_name == "ssebench-env-demo-1-one"
    assert pairs(first.environment_options(), "--name") == [first.environment_name]
    assert {first.source_volume, first.socket_volume}.isdisjoint({second.source_volume, second.socket_volume})
    assert (
        len(SidecarPair(task_name="t", source_dir="/s", results="r", archive="a", network="n", difficulty=2).run_id)
        == 12
    )


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
