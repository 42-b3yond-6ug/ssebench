"""An in-memory Kubernetes cluster for the tests of the Kubernetes backend.

It keeps the objects that the backend creates and gives every Job one pod whose containers are in the
state the test sets. It also answers the commands the backend runs in the collector, from files that the
test puts into the pod's volumes.
"""

import base64
import io
import tarfile
from collections.abc import Iterator, Mapping
from typing import Any

from ssebench.backends.kubernetes.api import Kind, KubeError


def waiting(reason: str = "ContainerCreating", message: str = "") -> dict[str, Any]:
    return {"waiting": {"reason": reason, "message": message}}


def running() -> dict[str, Any]:
    return {"running": {"startedAt": "2026-01-01T00:00:00Z"}}


def terminated(code: int) -> dict[str, Any]:
    return {"terminated": {"exitCode": code, "reason": "Completed" if code == 0 else "Error"}}


def tar_bytes(files: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class FakeKube:
    """The cluster. `task` and `collector` are the container states of the run's pod."""

    def __init__(self, namespace: str = "runs") -> None:
        self.namespace = namespace
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[tuple[str, str, str]] = []
        self.task: dict[str, Any] = waiting()
        self.collector: dict[str, Any] = running()
        self.pod_phase = "Running"
        self.pod_conditions: list[dict[str, Any]] = []
        self.volumes: dict[str, bytes | Mapping[str, bytes]] = {"/results": {}, "/archive": {}}
        self.log_lines = ["first line", "second line"]
        self.execs: list[list[str]] = []
        self.released = False
        self.ignore_term = False
        self.fail: dict[str, KubeError] = {}
        self.job_conditions: list[dict[str, Any]] = []
        self.used: set[tuple[str, str]] = set()
        """Every (action, kind) that the backend called."""
        self._uid = 0

    # ---- the API ----

    def _check(self, action: str, kind: str) -> None:
        self.used.add((action, kind))
        error = self.fail.get(f"{action} {kind}")
        if error is not None:
            raise error

    def create(self, kind: Kind, body: Mapping[str, Any]) -> dict[str, Any]:
        self._check("create", kind)
        name = body["metadata"]["name"]
        if (kind, name) in self.objects:
            raise KubeError(f'{kind} "{name}" already exists', 409)
        self._uid += 1
        stored = {
            **body,
            "metadata": {**body["metadata"], "uid": f"uid-{self._uid}", "creationTimestamp": "2026-01-01T00:00:00Z"},
        }
        self.objects[(kind, name)] = stored
        self.calls.append(("create", kind, name))
        if kind == "job":
            template = body["spec"]["template"]
            pod_name = f"{name}-abcde"
            self.objects[("pod", pod_name)] = {
                "metadata": {
                    "name": pod_name,
                    "labels": {**template["metadata"]["labels"], "job-name": name},
                    "creationTimestamp": "2026-01-01T00:00:00Z",
                },
                "spec": template["spec"],
            }
        return stored

    def read(self, kind: Kind, name: str) -> dict[str, Any] | None:
        self._check("read", kind)
        obj = self.objects.get((kind, name))
        return self._view(kind, obj) if obj else None

    def find(self, kind: Kind, label_selector: str = "") -> list[dict[str, Any]]:
        self._check("find", kind)
        wanted = dict(item.split("=", 1) for item in label_selector.split(",") if item)
        found: list[dict[str, Any]] = []
        for (k, _), obj in self.objects.items():
            labels = obj["metadata"].get("labels", {})
            if k == kind and all(labels.get(key) == value for key, value in wanted.items()):
                found.append(self._view(kind, obj))
        return found

    def _view(self, kind: str, obj: dict[str, Any]) -> dict[str, Any]:
        if kind == "pod":
            status: dict[str, Any] = {"phase": self.pod_phase, "conditions": self.pod_conditions}
            if obj["metadata"].get("labels", {}).get("job-name"):
                status["containerStatuses"] = [
                    {"name": "task", "state": self.task},
                    {"name": "collector", "state": self.collector},
                ]
            return {**obj, "status": status}
        if kind == "job":
            return {**obj, "status": {"conditions": self.job_conditions}}
        return obj

    def patch(self, kind: Kind, name: str, body: Mapping[str, Any]) -> None:
        self._check("patch", kind)
        self.calls.append(("patch", kind, name))
        self.objects[(kind, name)]["metadata"].update(body.get("metadata", {}))

    def delete(self, kind: Kind, name: str, *, grace_seconds: int | None = None) -> None:
        self._check("delete", kind)
        self.calls.append(("delete", kind, name))
        self.objects.pop((kind, name), None)
        if kind == "job":
            for key in [k for k in self.objects if k[0] == "pod" and k[1].startswith(name + "-")]:
                del self.objects[key]

    def pod_log(
        self,
        pod: str,
        container: str,
        *,
        follow: bool = False,
        timestamps: bool = False,
        since_seconds: int | None = None,
    ) -> Iterator[str]:
        self._check("log", "pod")
        for index, line in enumerate(self.log_lines):
            yield f"2026-01-01T00:00:{index:02d}.000000000Z {line}" if timestamps else line

    def exec(self, pod: str, container: str, command: list[str]) -> Iterator[str]:
        self._check("exec", "pod")
        self.execs.append(command)
        script = command[-1]
        if "kill -TERM 1" in script:
            if not self.ignore_term:
                self.task = terminated(143)
            return
        if ": > /control/done" in script:
            self.released = True
            return
        for directory, content in self.volumes.items():
            if f"tar -cf - -C {directory} " in script:
                data = content if isinstance(content, bytes) else tar_bytes(content)
                text = base64.encodebytes(data).decode()
                for start in range(0, len(text), 4096):
                    yield text[start : start + 4096]
                return
        raise KubeError(f"unexpected command {command}")
