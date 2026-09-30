"""Reaching a Kubernetes run from outside: forwarded ports that outlive the command, and `kubectl exec` vectors."""

import os
import stat
import sys
import time
from pathlib import Path

import pytest

from ssebench.backends import BackendError
from ssebench.backends.kubernetes import KubernetesBackend, KubernetesConfig, KubernetesRun, forward
from ssebench.backends.kubernetes import backend as backend_module

from .fake_kube import FakeKube, running, terminated
from .test_kubernetes_backend import make_spec

FAKE_KUBECTL = f"""#!{sys.executable}
import json, os, socket, sys, time
with open(os.path.join(os.path.dirname(__file__), "kubectl.log"), "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if "port-forward" in sys.argv:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    print(f"Forwarding from 127.0.0.1:{{server.getsockname()[1]}} -> 4263", flush=True)
    while True:
        connection, _ = server.accept()
        connection.close()
"""


@pytest.fixture
def kubectl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `kubectl` on the PATH that logs its arguments, and answers `port-forward` like the real one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "kubectl"
    _ = script.write_text(FAKE_KUBECTL)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = bin_dir / "kubectl.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(forward.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    return log


@pytest.fixture
def kube() -> FakeKube:
    cluster = FakeKube()
    cluster.task = running()
    return cluster


@pytest.fixture
def backend(kube: FakeKube) -> KubernetesBackend:
    return KubernetesBackend(KubernetesConfig(context="kind-test"), api=kube)


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backend_module, "POLL_SECONDS", 0.01)


def start(backend: KubernetesBackend, tmp_path: Path) -> KubernetesRun:
    handle = backend.start(make_spec(tmp_path))
    assert isinstance(handle, KubernetesRun)
    handle.finished.set()
    return handle


def invocations(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_endpoint_forwards_a_port_once_and_reuses_it(backend: KubernetesBackend, tmp_path: Path, kubectl: Path) -> None:
    handle = start(backend, tmp_path)

    first = backend.endpoint(handle, 4263)
    second = backend.endpoint(handle, 4263)

    assert first == second and first.startswith("http://127.0.0.1:")
    [call] = invocations(kubectl)
    assert '"--context", "kind-test", "--namespace", "runs", "port-forward", "--address", "127.0.0.1"' in call
    assert f'"pod/{handle.name}-abcde", ":4263"' in call
    backend.cleanup(handle)


def test_the_forward_outlives_the_call_and_ends_with_the_run(
    backend: KubernetesBackend, tmp_path: Path, kubectl: Path
) -> None:
    import json

    handle = start(backend, tmp_path)
    _ = backend.endpoint(handle, 4263)
    [record] = forward.state_dir().glob("*.json")
    pid = json.loads(record.read_text())["pid"]

    assert forward._alive(pid)  # pyright: ignore[reportPrivateUsage]
    backend.cleanup(handle)

    deadline = time.monotonic() + 5
    while forward._alive(pid) and time.monotonic() < deadline:  # pyright: ignore[reportPrivateUsage]
        time.sleep(0.05)
    assert not forward._alive(pid)  # pyright: ignore[reportPrivateUsage]
    assert list(forward.state_dir().glob("*")) == []


def test_each_port_gets_its_own_forward(backend: KubernetesBackend, tmp_path: Path, kubectl: Path) -> None:
    handle = start(backend, tmp_path)

    assert backend.endpoint(handle, 4263) != backend.endpoint(handle, 4096)

    assert len(invocations(kubectl)) == 2
    backend.cleanup(handle)


def test_a_dead_forward_is_replaced(backend: KubernetesBackend, tmp_path: Path, kubectl: Path) -> None:
    import json
    import signal

    handle = start(backend, tmp_path)
    _ = backend.endpoint(handle, 4263)
    [record] = forward.state_dir().glob("*.json")
    os.kill(json.loads(record.read_text())["pid"], signal.SIGKILL)
    time.sleep(0.2)

    _ = backend.endpoint(handle, 4263)

    assert len(invocations(kubectl)) == 2
    backend.cleanup(handle)


def test_a_forward_that_does_not_come_up_is_an_error_with_kubectls_words(
    backend: KubernetesBackend, tmp_path: Path, kubectl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = kubectl.parent / "kubectl"
    _ = script.write_text(f"#!{sys.executable}\nimport sys\nprint('error: pods is forbidden')\nsys.exit(1)\n")
    handle = start(backend, tmp_path)

    with pytest.raises(BackendError, match="Could not forward the port: error: pods is forbidden"):
        _ = backend.endpoint(handle, 4263)


def test_a_run_that_is_not_running_has_no_endpoint(
    backend: KubernetesBackend, tmp_path: Path, kube: FakeKube, kubectl: Path
) -> None:
    kube.task = terminated(0)
    handle = start(backend, tmp_path)

    with pytest.raises(BackendError, match="is not running"):
        _ = backend.endpoint(handle, 4263)
    assert invocations(kubectl) == []


def test_without_kubectl_the_endpoint_says_so(
    backend: KubernetesBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = start(backend, tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(BackendError, match="needs kubectl on the PATH"):
        _ = backend.endpoint(handle, 4263)


def test_exec_argv_is_a_kubectl_exec_in_the_task_container(
    backend: KubernetesBackend, tmp_path: Path, kubectl: Path
) -> None:
    handle = start(backend, tmp_path)
    argv = backend.exec_argv(handle, ["ls", "-l", "a b"], tty=True)

    assert argv[0].endswith("kubectl") and backend.supports_exec
    assert argv[1:] == [
        "--context", "kind-test", "--namespace", "runs", "exec", "--stdin", "--tty",
        "--container", "task", f"{handle.name}-abcde", "--", "ls", "-l", "a b",
    ]  # fmt: skip
    assert "--stdin" not in backend.exec_argv(handle, ["true"])
    assert backend.exec_argv(handle, ["cat"], stdin=True).count("--stdin") == 1


def test_exec_argv_runs_as_a_user_in_a_directory_with_the_arguments_quoted(
    backend: KubernetesBackend, tmp_path: Path, kubectl: Path
) -> None:
    handle = start(backend, tmp_path)

    argv = backend.exec_argv(handle, ["echo", "$HOME; id"], user="model", workdir="/src/my project")

    assert argv[argv.index("--") + 1 :] == [
        "su", "-s", "/bin/sh", "model", "-c",
        "sh -c 'cd '\"'\"'/src/my project'\"'\"' && exec echo '\"'\"'$HOME; id'\"'\"''",
    ]  # fmt: skip


def test_environment_values_cannot_be_passed_and_are_refused(
    backend: KubernetesBackend, tmp_path: Path, kubectl: Path
) -> None:
    handle = start(backend, tmp_path)

    with pytest.raises(BackendError, match="cannot pass environment variables"):
        _ = backend.exec_argv(handle, ["env"], env_names=["SSE_API_KEY"])


def test_a_run_reports_when_it_was_created(backend: KubernetesBackend, tmp_path: Path) -> None:
    _ = start(backend, tmp_path)

    [info] = backend.list_runs()

    assert info.created_at == "2026-01-01T00:00:00Z"
