#!/usr/bin/env python3
"""Benchmark-integrity bypass tests.

Starts a real run in either mode, holds it in the agent phase, and runs
``fake_agent.sh`` as the unprivileged ``model`` user in the agent's container
to prove that none of the known bypasses work while the allowed actions still
do. Also checks the host-side, post-run path: the reference patch is served
over HTTP :4263 only after the agent phase ends.

- sandbox: one container holds the daemon and the agent.
- sidecar: the agent container and the task container (the daemon) are laid
  out exactly as ``ssebench run --mode sidecar`` lays them out.

Runnable two ways:
  - as a script:  uv run python tests/integrity/test_bypass.py [--mode MODE] [difficulty ...]
  - under pytest: uv run pytest tests/integrity -m integrity

The images must already be built, for example by one `ssebench run` of the
task in each mode; a mode whose images are missing is skipped. Point at them
with:
  SSEBENCH_INTEGRITY_IMAGE               sandbox tool image
  SSEBENCH_INTEGRITY_SIDECAR_ENV_IMAGE   sidecar environment (task) image
  SSEBENCH_INTEGRITY_SIDECAR_AGENT_IMAGE sidecar agent runtime image
  SSEBENCH_INTEGRITY_SOURCE              source dir inside the images; default: /src/gjson
The defaults are the images `ssebench` builds for gjson-196-bf4efcb, from
SSEBENCH_REGISTRY and the current version. Sidecar mode needs the uv workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

TASK = "gjson-196-bf4efcb"
MODES = ("sandbox", "sidecar")


def _default_images() -> tuple[str, str, str]:
    """The sandbox tool image and the sidecar environment and agent runtime images `ssebench` builds for TASK."""
    try:
        from ssebench.middleware.tools import (
            DOCKER_IMAGE_PREFIX_SANDBOX,
            DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT,
            DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON,
        )
        from ssebench.pipe import TAG
    except ImportError:  # outside the uv workspace, which sidecar mode needs anyway
        registry = os.environ.get("SSEBENCH_REGISTRY", "ghcr.io/42-b3yond-6ug/ssebench").rstrip("/")
        return f"{registry}/tool/{TASK}", "", ""
    return (
        f"{DOCKER_IMAGE_PREFIX_SANDBOX}/{TASK}:{TAG}",
        f"{DOCKER_IMAGE_PREFIX_SIDECAR_ENVIRON}/{TASK}:{TAG}",
        f"{DOCKER_IMAGE_PREFIX_SIDECAR_AGENTRT}:{TAG}",
    )


_SANDBOX_IMAGE, _SIDECAR_ENV_IMAGE, _SIDECAR_AGENT_IMAGE = _default_images()
IMAGE = os.environ.get("SSEBENCH_INTEGRITY_IMAGE") or _SANDBOX_IMAGE
SIDECAR_ENV_IMAGE = os.environ.get("SSEBENCH_INTEGRITY_SIDECAR_ENV_IMAGE") or _SIDECAR_ENV_IMAGE
SIDECAR_AGENT_IMAGE = os.environ.get("SSEBENCH_INTEGRITY_SIDECAR_AGENT_IMAGE") or _SIDECAR_AGENT_IMAGE
SOURCE_DIR = os.environ.get("SSEBENCH_INTEGRITY_SOURCE", "/src/gjson")
NETWORK = "ssebench-integrity-testnet"
FAKE_AGENT = Path(__file__).with_name("fake_agent.sh")
# The same path in both modes; in sidecar mode it is on a volume the two containers share.
ADMIN_SOCKET = "/run/ssebench/admin.sock"

DIFFICULTIES = (0, 2, 4)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def missing_images(mode: str) -> list[str]:
    images = [IMAGE] if mode == "sandbox" else [SIDECAR_ENV_IMAGE, SIDECAR_AGENT_IMAGE]
    return [
        i or "<needs the uv workspace>" for i in images if not i or _run(["docker", "image", "inspect", i]).returncode
    ]


def ensure_network() -> None:
    if _run(["docker", "network", "inspect", NETWORK]).returncode != 0:
        # Internal network: reaches sibling containers but not the internet, so
        # the fake agent's egress probe fails as the restricted policy requires.
        subprocess.run(["docker", "network", "create", "--internal", NETWORK], check=True)


def remove_network() -> None:
    _run(["docker", "network", "rm", NETWORK])


@dataclass
class Deployment:
    """A run held in its agent phase."""

    agent: str
    """The container the agent runs in; the fake agent runs there as `model`."""
    daemon: str
    """The container the daemon runs in."""
    daemon_socket: str
    cleanup: Callable[[], None]
    probe_env: dict[str, str] = field(default_factory=dict)
    """The daemon's endpoints for fake_agent.sh, when they differ from the sandbox layout."""


def start_sandbox(difficulty: int) -> Deployment:
    name = f"integrity-bypass-{difficulty}-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "--network",
            NETWORK,
            "--tmpfs",
            "/tmp/sse-archive",
            "-e",
            "SSE_ARCHIVE=/tmp/sse-archive",
            "-e",
            f"SSE_DIFFICULTY={difficulty}",
            # Hold the agent phase open so we can probe as `model`.
            IMAGE,
            "sleep",
            "1200",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return Deployment(agent=name, daemon=name, daemon_socket="/tmp/sse.sock", cleanup=lambda: stop_container(name))


def start_sidecar(difficulty: int) -> Deployment:
    from ssebench.runner import SidecarPair
    from ssebench.runner.runner import SIDECAR_DAEMON_SOCKET

    run_id = uuid.uuid4().hex[:12]
    # A volume rather than a host directory, so no root-owned files are left behind.
    archive = f"integrity-{run_id}-archive"
    pair = SidecarPair(
        task_name=TASK,
        source_dir=SOURCE_DIR,
        archive=archive,
        network=NETWORK,
        difficulty=difficulty,
        run_id=run_id,
    )
    agent = f"integrity-sidecar-{difficulty}-{run_id}"

    def cleanup() -> None:
        stop_container(agent)
        pair.remove()
        _run(["docker", "volume", "rm", archive])

    try:
        subprocess.run(["docker", "volume", "create", archive], check=True, stdout=subprocess.DEVNULL)
        pair.create_volumes()
        subprocess.run(
            ["docker", "run", "-d", *pair.environment_options(), SIDECAR_ENV_IMAGE],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            # Hold the agent phase open so we can probe as `model`.
            ["docker", "run", "-d", "--name", agent, *pair.agent_options(), SIDECAR_AGENT_IMAGE, "sleep", "1200"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    except BaseException:
        cleanup()
        raise
    return Deployment(
        agent=agent,
        daemon=pair.environment_name,
        daemon_socket=SIDECAR_DAEMON_SOCKET,
        probe_env={
            "SSE_DAEMON_SOCKET": SIDECAR_DAEMON_SOCKET,
            "SSE_ADMIN_SOCKET": ADMIN_SOCKET,
            "SSE_DAEMON_HTTP": f"http://{pair.environment_name}:4263",
        },
        cleanup=cleanup,
    )


def start(mode: str, difficulty: int) -> Deployment:
    ensure_network()
    return start_sidecar(difficulty) if mode == "sidecar" else start_sandbox(difficulty)


def wait_for_daemon(dep: Deployment, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = _run(
            [
                "docker",
                "exec",
                dep.agent,
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--unix-socket",
                dep.daemon_socket,
                "http://d/version",
            ]
        )
        if probe.stdout.strip() == "200":
            return
        # Fail fast if a container died.
        for name in {dep.agent, dep.daemon}:
            if _run(["docker", "inspect", "-f", "{{.State.Running}}", name]).stdout.strip() != "true":
                logs = _run(["docker", "logs", name]).stdout
                raise RuntimeError(f"container {name} exited early:\n{logs}")
        time.sleep(2)
    raise RuntimeError(f"daemon in {dep.daemon} did not become ready in {timeout}s")


def wait_for_http(ip: str, timeout: int = 60) -> None:
    """Wait for the daemon's HTTP :4263 listener to answer from the host.

    The unix socket comes up a moment before the HTTP listener binds, so a host
    request can otherwise race and fail to connect.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = _run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://{ip}:4263/version"]).stdout.strip()
        if code == "200":
            return
        time.sleep(1)
    raise RuntimeError(f"HTTP :4263 on {ip} did not become ready in {timeout}s")


def container_ip(name: str) -> str:
    out = _run(
        [
            "docker",
            "inspect",
            name,
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
        ]
    ).stdout.strip()
    if not out:
        raise RuntimeError(f"no IP for container {name}")
    return out


def stop_container(name: str) -> None:
    _run(["docker", "rm", "-f", name])


def run_fake_agent(dep: Deployment, difficulty: int) -> subprocess.CompletedProcess[str]:
    subprocess.run(["docker", "cp", str(FAKE_AGENT), f"{dep.agent}:/tmp/fake_agent.sh"], check=True)
    env = [arg for name, value in dep.probe_env.items() for arg in ("-e", f"{name}={value}")]
    return _run(
        [
            "docker",
            "exec",
            "--user",
            "model",
            *env,
            dep.agent,
            "bash",
            "/tmp/fake_agent.sh",
            str(difficulty),
            SOURCE_DIR,
        ]
    )


def check_bypasses(mode: str, difficulty: int) -> None:
    """Run the fake agent at one difficulty; raise on any failed check."""
    dep = start(mode, difficulty)
    try:
        wait_for_daemon(dep)
        result = run_fake_agent(dep, difficulty)
        print(result.stdout)
        if result.returncode != 0:
            raise AssertionError(
                f"integrity bypass ({mode}) at difficulty {difficulty} succeeded:\n{result.stdout}\n{result.stderr}"
            )
    finally:
        dep.cleanup()


def check_reference_patch_phase(mode: str) -> None:
    """The reference patch is withheld during the agent phase and served after."""
    dep = start(mode, 2)
    try:
        wait_for_daemon(dep)
        ip = container_ip(dep.daemon)
        wait_for_http(ip)

        # During the agent phase: HTTP :4263 must refuse the reference patch.
        during = _run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://{ip}:4263/reference/patch"]
        ).stdout.strip()
        assert during == "403", f"reference patch served mid-run (HTTP {during})"

        # The entrypoint, as root in the agent's container, would signal this
        # over the admin socket when the agent exits; do it here to exercise the unlock.
        signal = _run(
            [
                "docker",
                "exec",
                dep.agent,
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--unix-socket",
                ADMIN_SOCKET,
                "-X",
                "POST",
                "http://d/admin/agent_exited",
            ]
        ).stdout.strip()
        assert signal == "200", f"admin agent_exited failed (HTTP {signal})"

        # After the phase ends: the web UI (host) can read it over :4263.
        after = _run(["curl", "-s", f"http://{ip}:4263/reference/patch"]).stdout.strip()
        payload = json.loads(after)
        assert payload.get("diff", "").strip(), "reference patch empty post-run"
    finally:
        dep.cleanup()


# ----------------------------------------------------------------------------
# pytest interface
# ----------------------------------------------------------------------------

pytestmark = pytest.mark.integrity


@pytest.fixture(scope="session", autouse=True)
def _network():
    yield
    remove_network()


@pytest.fixture(params=MODES)
def mode(request: pytest.FixtureRequest) -> str:
    if missing := missing_images(request.param):
        pytest.skip(f"{request.param} images not built: {', '.join(missing)}")
    return request.param


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_no_bypass(mode: str, difficulty: int):
    check_bypasses(mode, difficulty)


def test_reference_patch_phase_gate(mode: str):
    check_reference_patch_phase(mode)


# ----------------------------------------------------------------------------
# script interface
# ----------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Benchmark-integrity bypass tests")
    parser.add_argument("--mode", choices=MODES, default="sandbox")
    parser.add_argument("difficulty", type=int, nargs="*", default=list(DIFFICULTIES))
    args = parser.parse_args(argv)

    if missing := missing_images(args.mode):
        print(f"{args.mode} images not built: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        for d in args.difficulty:
            print(f"\n### {args.mode}, difficulty {d} ###")
            check_bypasses(args.mode, d)
        print(f"\n### {args.mode}, reference-patch phase gate ###")
        check_reference_patch_phase(args.mode)
    except AssertionError as e:
        print(f"\nINTEGRITY TEST FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        remove_network()
    print(f"\nAll integrity bypass tests passed ({args.mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
