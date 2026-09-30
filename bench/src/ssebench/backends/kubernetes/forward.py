"""Port-forwards that outlive the command that started them, so that a run's ports can be reached from outside the cluster.

`ssebench runs endpoint` is a short-lived command, but the URL it prints has to keep working for the tool
that asked. So the forward is a detached `kubectl port-forward` on a local port of its own, recorded in a
file, and the next call for the same pod and port finds it and reuses it. It listens on 127.0.0.1 only. It
ends by itself when the pod does; `stop_forwards` ends it earlier.
"""

import contextlib
import fcntl
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from ssebench.backends.base import BackendError

logger = logging.getLogger(__name__)

START_TIMEOUT_SECONDS: Final = 20.0
_LISTENING = re.compile(r"Forwarding from 127\.0\.0\.1:(\d+) ->")


def state_dir() -> Path:
    """A directory for the records of the forwards, private to this user."""
    directory = Path(tempfile.gettempdir()) / f"ssebench-k8s-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory


def kubectl_path() -> str:
    found = shutil.which("kubectl")
    if found is None:
        raise BackendError("This needs kubectl on the PATH: it forwards ports and runs commands in the pod")
    return found


def kubectl_base(namespace: str, context: str | None) -> list[str]:
    """`kubectl` with the namespace and context of the backend. The kubeconfig is found as kubectl does."""
    return [kubectl_path(), *(["--context", context] if context else []), "--namespace", namespace]


def _record(namespace: str, pod: str, port: int) -> Path:
    return state_dir() / f"{namespace}.{pod}.{port}.json"


def _alive(pid: int) -> bool:
    with contextlib.suppress(ChildProcessError):
        # A forward started by this process becomes a zombie when it ends, which `kill` still finds.
        _ = os.waitpid(pid, os.WNOHANG)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def forward(namespace: str, context: str | None, pod: str, port: int) -> int:
    """The local port that reaches `port` of `pod`: the recorded forward if it still works, else a new one.

    Raises:
        BackendError: If kubectl is missing or the forward does not come up.
    """
    command = [*kubectl_base(namespace, context), "port-forward", "--address", "127.0.0.1", f"pod/{pod}", f":{port}"]
    record = _record(namespace, pod, port)
    with _locked(record):
        try:
            known = json.loads(record.read_text())
            if _alive(known["pid"]) and _accepts(known["local"]):
                return int(known["local"])
        except (OSError, ValueError, KeyError):
            pass
        return _start(record, command)


def _start(record: Path, command: list[str]) -> int:
    log = record.with_suffix(".log")
    with open(log, "w") as out:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        found = _LISTENING.search(log.read_text())
        if found:
            local = int(found.group(1))
            _ = record.write_text(json.dumps({"pid": process.pid, "local": local}))
            return local
        if process.poll() is not None:
            break
        time.sleep(0.1)
    if process.poll() is None:
        process.terminate()
    _ = process.wait()
    raise BackendError(
        f"Could not forward the port: {log.read_text().strip() or 'kubectl port-forward printed nothing'}"
    )


def stop_forwards(namespace: str, pod: str) -> None:
    """End the forwards to `pod`. They end by themselves when the pod goes; this only makes it prompt."""
    for record in state_dir().glob(f"{namespace}.{pod}.*.json"):
        try:
            pid = int(json.loads(record.read_text())["pid"])
            if _alive(pid):
                os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError, KeyError) as e:
            logger.debug(f"Could not end the forward {record.name}: {e}")
        for leftover in (record, record.with_suffix(".log"), record.with_suffix(".lock")):
            leftover.unlink(missing_ok=True)
