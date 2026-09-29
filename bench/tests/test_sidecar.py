"""The container layout of a sidecar run: what each container gets, and what the agent never does."""

from pathlib import Path

from ssebench.runner import SidecarPair
from ssebench.runner.runner import ARCHIVE_PATH, SIDECAR_DAEMON_SOCKET, SIDECAR_SOCKET_DIR


def make_pair(**kw: object) -> SidecarPair:
    fields: dict[str, object] = {
        "task_name": "Demo-1",
        "source_dir": "/src/demo",
        "archive": "/host/results",
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
        assert pairs(options, "-v")[:3] == [
            f"/host/results:{ARCHIVE_PATH}",
            "ssebench-abc123-source:/src/demo",
            f"ssebench-abc123-sockets:{SIDECAR_SOCKET_DIR}",
        ]


def test_the_agent_container_never_mounts_the_task_files() -> None:
    options = make_pair().agent_options({"SSE_API_KEY": "sk-x"}, result_file=Path("/host/results/result.json"))

    targets = [volume.split(":")[1] for volume in pairs(options, "-v")]
    assert not any(target == "/ssebench" or target.startswith("/ssebench/") for target in targets)
    assert "/ssebench-repo" not in targets
    assert "/host/results/result.json:/sse_result" in pairs(options, "-v")
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
    assert len(SidecarPair(task_name="t", source_dir="/s", archive="a", network="n", difficulty=2).run_id) == 12
