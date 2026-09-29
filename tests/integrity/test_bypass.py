#!/usr/bin/env python3
"""Benchmark-integrity bypass tests.

Starts a real sandbox container, holds it in the agent phase, and runs
``fake_agent.sh`` as the unprivileged ``model`` user to prove that none of the
known bypasses work while the allowed actions still do. Also checks the
host-side, post-run path: the reference patch is served over HTTP :4263 only
after the agent phase ends.

Runnable two ways:
  - as a script:  uv run python tests/integrity/test_bypass.py [difficulty ...]
  - under pytest: uv run pytest tests/integrity -m integrity

The sandbox tool image must already be built, for example by one
`ssebench run` of the task. Point at it with:
  SSEBENCH_INTEGRITY_IMAGE   (default: the tool image `ssebench` builds for
                              gjson-196-bf4efcb, from SSEBENCH_REGISTRY and the
                              current version)
  SSEBENCH_INTEGRITY_SOURCE  (source dir inside the image; default: /src/gjson)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

TASK = "gjson-196-bf4efcb"


def _default_image() -> str:
    try:
        from ssebench.pipe import REGISTRY, TAG
    except ImportError:  # outside the uv workspace
        registry = os.environ.get("SSEBENCH_REGISTRY", "ghcr.io/42-b3yond-6ug/ssebench").rstrip("/")
        return f"{registry}/tool/{TASK}"
    return f"{REGISTRY}/tool/{TASK}:{TAG}"


IMAGE = os.environ.get("SSEBENCH_INTEGRITY_IMAGE") or _default_image()
SOURCE_DIR = os.environ.get("SSEBENCH_INTEGRITY_SOURCE", "/src/gjson")
NETWORK = "ssebench-integrity-testnet"
FAKE_AGENT = Path(__file__).with_name("fake_agent.sh")

DIFFICULTIES = (0, 2, 4)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def image_available() -> bool:
    return _run(["docker", "image", "inspect", IMAGE]).returncode == 0


def ensure_network() -> None:
    if _run(["docker", "network", "inspect", NETWORK]).returncode != 0:
        # Internal network: reaches sibling containers but not the internet, so
        # the fake agent's egress probe fails as the restricted policy requires.
        subprocess.run(["docker", "network", "create", "--internal", NETWORK], check=True)


def remove_network() -> None:
    _run(["docker", "network", "rm", NETWORK])


def start_container(difficulty: int) -> str:
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
    return name


def wait_for_daemon(name: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = _run(
            [
                "docker",
                "exec",
                name,
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--unix-socket",
                "/tmp/sse.sock",
                "http://d/version",
            ]
        )
        if probe.stdout.strip() == "200":
            return
        # Fail fast if the container died.
        if _run(["docker", "inspect", "-f", "{{.State.Running}}", name]).stdout.strip() != "true":
            logs = _run(["docker", "logs", name]).stdout
            raise RuntimeError(f"container {name} exited early:\n{logs}")
        time.sleep(2)
    raise RuntimeError(f"daemon in {name} did not become ready in {timeout}s")


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


def run_fake_agent(name: str, difficulty: int) -> subprocess.CompletedProcess[str]:
    subprocess.run(["docker", "cp", str(FAKE_AGENT), f"{name}:/tmp/fake_agent.sh"], check=True)
    return _run(
        [
            "docker",
            "exec",
            "--user",
            "model",
            name,
            "bash",
            "/tmp/fake_agent.sh",
            str(difficulty),
            SOURCE_DIR,
        ]
    )


def check_bypasses(difficulty: int) -> None:
    """Run the fake agent at one difficulty; raise on any failed check."""
    ensure_network()
    name = start_container(difficulty)
    try:
        wait_for_daemon(name)
        result = run_fake_agent(name, difficulty)
        print(result.stdout)
        if result.returncode != 0:
            raise AssertionError(
                f"integrity bypass at difficulty {difficulty} succeeded:\n{result.stdout}\n{result.stderr}"
            )
    finally:
        stop_container(name)


def check_reference_patch_phase() -> None:
    """The reference patch is withheld during the agent phase and served after."""
    ensure_network()
    name = start_container(2)
    try:
        wait_for_daemon(name)
        ip = container_ip(name)
        wait_for_http(ip)

        # During the agent phase: HTTP :4263 must refuse the reference patch.
        during = _run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://{ip}:4263/reference/patch"]
        ).stdout.strip()
        assert during == "403", f"reference patch served mid-run (HTTP {during})"

        # The entrypoint would signal this over the admin socket when the agent
        # exits; do it here (as root) to exercise the unlock.
        signal = _run(
            [
                "docker",
                "exec",
                name,
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--unix-socket",
                "/run/ssebench/admin.sock",
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
        stop_container(name)


# ----------------------------------------------------------------------------
# pytest interface
# ----------------------------------------------------------------------------

pytestmark = pytest.mark.integrity


@pytest.fixture(scope="session", autouse=True)
def _require_image():
    if not image_available():
        pytest.skip(f"integrity image not built: {IMAGE}")
    yield
    remove_network()


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_no_bypass(difficulty: int):
    check_bypasses(difficulty)


def test_reference_patch_phase_gate():
    check_reference_patch_phase()


# ----------------------------------------------------------------------------
# script interface
# ----------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if not image_available():
        print(f"integrity image not built: {IMAGE}", file=sys.stderr)
        return 2
    difficulties = [int(a) for a in argv] or list(DIFFICULTIES)
    try:
        for d in difficulties:
            print(f"\n### difficulty {d} ###")
            check_bypasses(d)
        print("\n### reference-patch phase gate ###")
        check_reference_patch_phase()
    except AssertionError as e:
        print(f"\nINTEGRITY TEST FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        remove_network()
    print("\nAll integrity bypass tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
