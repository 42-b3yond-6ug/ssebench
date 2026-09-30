"""The Kubernetes backend: a run is one Job.

The Job's pod has the task container, which runs a prebuilt image as it is, and a collector that only
waits (see `manifests`). The run's environment and files are a Secret, its network policy a NetworkPolicy,
both owned by the Job. Results are two `emptyDir` volumes; once the task container has exited, the backend
reads them out of the collector through the API, as `kubectl cp` does, and lets the collector exit. Nothing
needs a storage class or a shared file system, and the runner may be outside the cluster.
"""

import base64
import binascii
import logging
import shlex
import signal
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from typing import IO, Any, override

from ssebench.backends.base import (
    RUN_ID_LABEL,
    STOP_GRACE_SECONDS,
    Backend,
    BackendError,
    ImageRequest,
    Images,
    ImageUnavailableError,
    ProxyEndpoint,
    RunHandle,
    RunInfo,
    RunSpec,
    RunState,
)
from ssebench.backends.images import prebuilt_images
from ssebench.backends.kubernetes import archive, config, forward, manifests
from ssebench.backends.kubernetes.api import INSTALL_HINT, Kind, KubeApi, KubeClient, KubeError
from ssebench.backends.kubernetes.config import KubernetesConfig
from ssebench.errors import UserError

logger = logging.getLogger(__name__)

POLL_SECONDS = 1.0
"""How often `wait` reads the pod's state."""
MAX_API_FAILURES = 10
"""How many calls in a row may fail before `wait` gives up on the cluster."""
IMAGE_PULL_PATIENCE = 90.0
"""How long a container may stay in an image pull error before the run fails; the kubelet keeps retrying."""
LOG_JOIN_SECONDS = 15.0
"""How long `wait` gives the log forwarder to write the container's last lines."""

# Reasons for which a container that is waiting will not start without someone changing the pod.
FATAL_WAITING = frozenset({"InvalidImageName", "CreateContainerConfigError", "ErrImageNeverPull"})
IMAGE_PULL_ERRORS = frozenset({"ErrImagePull", "ImagePullBackOff"})

SIDECAR_UNSUPPORTED = (
    "Sidecar mode is not supported by the Kubernetes backend: its two containers would need the project's "
    "files copied into a shared volume before they start. Use sandbox mode."
)


@dataclass(kw_only=True)
class KubernetesRun(RunHandle):
    """A run on the cluster: `name` is the Job, and the Secret and NetworkPolicy of the run share it."""

    pod: str = ""
    stopped: bool = False
    """Whether `stop` was called. A stopped run whose pod is gone ended by our own doing."""
    forwarder: threading.Thread | None = field(default=None, repr=False)
    finished: threading.Event = field(default_factory=threading.Event, repr=False)
    """Set when the run no longer needs its log forwarded."""
    pulling_since: float | None = None


def _status(pod: Mapping[str, Any], container: str) -> Mapping[str, Any]:
    """The status of a container of `pod`; empty until the kubelet reports one."""
    for status in pod.get("status", {}).get("containerStatuses") or []:
        if status.get("name") == container:
            return status
    return {}


def _state(status: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    """`waiting`, `running` or `terminated`, with the details of that state."""
    for name in ("terminated", "running", "waiting"):
        detail = (status.get("state") or {}).get(name)
        if detail is not None:
            return name, detail
    return "waiting", {}


def _describe_pod(pod: Mapping[str, Any]) -> str:
    """Why a pod is not running, in the words of its conditions and of the task container."""
    status = pod.get("status", {})
    reasons: list[str] = []
    for condition in status.get("conditions") or []:
        if condition.get("status") == "False" and condition.get("message"):
            reasons.append(f"{condition.get('reason', condition.get('type'))}: {condition['message']}")
    _, detail = _state(_status(pod, manifests.TASK_CONTAINER))
    if detail.get("reason"):
        reasons.append(f"{detail['reason']}: {detail.get('message', '')}".rstrip(": "))
    if status.get("reason"):
        reasons.append(f"{status['reason']}: {status.get('message', '')}".rstrip(": "))
    return "; ".join(reasons) or "no reason reported"


def _timestamp(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _decode(chunks: Iterator[str], out: IO[bytes]) -> None:
    """Write the bytes that the base64 text in `chunks` stands for to `out`, without holding them all."""
    pending = ""
    for chunk in chunks:
        pending += "".join(chunk.split())
        usable = len(pending) - len(pending) % 4
        _ = out.write(base64.b64decode(pending[:usable], validate=True))
        pending = pending[usable:]
    if pending:
        _ = out.write(base64.b64decode(pending, validate=True))


class KubernetesBackend(Backend):
    """Runs on the cluster that the kubeconfig, or the pod's service account, points to.

    It runs prebuilt images only. `config` holds the settings; by default they are the `SSEBENCH_K8S_*`
    settings. `api` is the cluster; by default the official client, created on first use.
    """

    name = "kubernetes"
    builds_images = False
    supports_exec = True

    def __init__(self, config: KubernetesConfig | None = None, api: KubeApi | None = None) -> None:
        if api is None and find_spec("kubernetes") is None:
            raise BackendError(INSTALL_HINT)
        self.config = config or KubernetesConfig.from_settings()
        self._api = api
        self._lock = threading.Lock()

    @property
    def api(self) -> KubeApi:
        with self._lock:
            if self._api is None:
                try:
                    self._api = KubeClient(self.config.namespace, self.config.context)
                except KubeError as e:
                    raise BackendError(str(e)) from e
            return self._api

    @override
    def proxy(self) -> ProxyEndpoint:
        namespace = self.api.namespace
        return ProxyEndpoint(
            host_url=config.host_url(self.config, namespace), service_url=config.service_url(self.config, namespace)
        )

    # ==================== images ====================

    @override
    def prepare_images(self, request: ImageRequest) -> Images:
        if request.mode == "sidecar":
            raise UserError(SIDECAR_UNSUPPORTED)
        if not request.prebuilt:
            raise UserError("The kubernetes backend runs prebuilt images; use --prebuilt")
        # The nodes pull the images, so all that can be checked here is the access to the cluster.
        try:
            _ = self.api.find("job", f"{manifests.MANAGED_BY[0]}={manifests.MANAGED_BY[1]}")
        except KubeError as e:
            raise ImageUnavailableError(f"Cannot use the cluster (namespace {self.api.namespace}): {e}") from e
        return prebuilt_images(request)

    @override
    def copy_from_image(self, image: str, path: PurePosixPath, dest: Path, platform: str | None = None) -> None:
        name = f"ssebench-copy-{uuid.uuid4().hex[:10]}"
        body = manifests.copy_pod(image, str(path), name, self.config)
        try:
            _ = self.api.create("pod", body)
        except (KubeError, BackendError) as e:
            raise RuntimeError(f"Could not start a pod to copy {path} from {image}: {e}") from e
        try:
            finished = self._wait_copy(name)
            if finished != "Succeeded":
                raise RuntimeError(f"Could not copy {path} from {image}: the pod {finished.lower()}")
            with dest.open("wb") as out:
                _decode(self.api.pod_log(name, "copy"), out)
        except (KubeError, binascii.Error, OSError) as e:
            raise RuntimeError(f"Could not copy {path} from {image}: {e}") from e
        finally:
            try:
                self.api.delete("pod", name, grace_seconds=0)
            except KubeError as e:
                logger.warning(f"Could not remove the pod {name}: {e}")

    def _wait_copy(self, name: str) -> str:
        """The phase in which the copy pod ended: `Succeeded`, or `Failed` with the reason logged."""
        started = time.monotonic()
        while True:
            pod = self.api.read("pod", name)
            if pod is None:
                raise RuntimeError(f"The pod {name} disappeared")
            phase = pod.get("status", {}).get("phase", "")
            if phase in ("Succeeded", "Failed"):
                if phase == "Failed":
                    logger.error(f"The copy pod failed: {_describe_pod(pod)}")
                return phase
            waiting = _state(_status(pod, "copy"))
            if waiting[0] == "waiting" and waiting[1].get("reason") in FATAL_WAITING | IMAGE_PULL_ERRORS:
                if time.monotonic() - started > IMAGE_PULL_PATIENCE:
                    raise RuntimeError(f"The image cannot be started: {_describe_pod(pod)}")
            if time.monotonic() - started > self.config.start_timeout + 300:
                raise RuntimeError(f"The copy pod did not finish in time: {_describe_pod(pod)}")
            time.sleep(POLL_SECONDS)

    # ==================== the run ====================

    @override
    def start(self, spec: RunSpec) -> RunHandle:
        if spec.sidecar is not None:
            raise BackendError(SIDECAR_UNSUPPORTED)
        api = self.api
        name = manifests.object_name(spec.run_id)
        try:
            artifacts = manifests.read_artifacts(spec.artifacts)
        except OSError as e:
            raise BackendError(f"Cannot read a file for the run: {e}") from e

        proxy_url = config.service_url(self.config, api.namespace)
        handle = KubernetesRun(run_id=spec.run_id, name=name, keep=spec.keep)
        try:
            _ = api.create("networkpolicy", manifests.network_policy(spec, self.config, name, api.namespace, proxy_url))
            _ = api.create("secret", manifests.secret(spec, name, artifacts))
            job = api.create("job", manifests.job(spec, self.config, name, artifacts))
            owned: tuple[Kind, ...] = ("secret", "networkpolicy")
            owner = [
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "name": name,
                    "uid": job["metadata"]["uid"],
                    "blockOwnerDeletion": False,
                }
            ]
            for kind in owned:
                api.patch(kind, name, {"metadata": {"ownerReferences": owner}})
        except KubeError as e:
            self._remove(name)
            reason = f"the name {name} is taken by another run" if e.status == 409 else str(e)
            raise BackendError(f"Could not start the run {spec.run_id}: {reason}") from e
        logger.info(f"Started the job {name} in namespace {api.namespace}")

        handle.forwarder = threading.Thread(target=self._forward_logs, args=(handle,), name=f"logs-{name}", daemon=True)
        handle.forwarder.start()
        return handle

    def _remove(self, name: str) -> None:
        """Delete the objects of a run, best effort. The Job goes first, and takes the pod with it."""
        kinds: tuple[Kind, ...] = ("job", "secret", "networkpolicy")
        for kind in kinds:
            try:
                self.api.delete(kind, name)
            except KubeError as e:
                logger.warning(f"Could not delete the {kind} {name}: {e}")

    def _pod(self, handle: KubernetesRun) -> dict[str, Any] | None:
        """The run's newest pod, or None while the Job has none."""
        pods = self.api.find("pod", f"job-name={handle.name}")
        if not pods:
            return None
        pod = max(pods, key=lambda p: p["metadata"].get("creationTimestamp", ""))
        handle.pod = pod["metadata"]["name"]
        return pod

    def _forward_logs(self, handle: KubernetesRun) -> None:
        """Copy the task container's output to this process's stdout as it is written, until it exits.

        A stream that ends before the container does is resumed from the last line written.
        """
        last: datetime | None = None
        try:
            while not handle.finished.is_set():
                pod = self._pod(handle)
                if pod is None or not self._started(pod):
                    _ = handle.finished.wait(POLL_SECONDS)
                    continue
                since = max(1, int((datetime.now(UTC) - last).total_seconds()) + 1) if last else None
                for raw in self.api.pod_log(
                    handle.pod, manifests.TASK_CONTAINER, follow=True, timestamps=True, since_seconds=since
                ):
                    stamp, _, line = raw.partition(" ")
                    moment = _timestamp(stamp)
                    if moment is not None:
                        if last is not None and moment <= last:
                            continue
                        last = moment
                    _ = sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                pod = self._pod(handle)
                if pod is not None and _state(_status(pod, manifests.TASK_CONTAINER))[0] == "terminated":
                    return
                _ = handle.finished.wait(POLL_SECONDS)
        except (KubeError, BackendError) as e:
            logger.warning(f"Stopped forwarding the output of {handle.name}: {e}")

    @staticmethod
    def _started(pod: Mapping[str, Any]) -> bool:
        return _state(_status(pod, manifests.TASK_CONTAINER))[0] != "waiting"

    @override
    def wait(self, handle: RunHandle, timeout: float | None = None) -> int:
        assert isinstance(handle, KubernetesRun)
        give_up = None if timeout is None else time.monotonic() + timeout
        start_by = time.monotonic() + self.config.start_timeout
        failures = 0
        while True:
            try:
                status = self._poll(handle, start_by)
                failures = 0
            except KubeError as e:
                failures += 1
                if failures >= MAX_API_FAILURES:
                    raise BackendError(f"Lost the cluster while waiting for {handle.name}: {e}") from e
                status = None
            if status is not None:
                self._join_forwarder(handle)
                return status
            if give_up is not None and time.monotonic() >= give_up:
                raise TimeoutError(f"The run {handle.run_id} is still running after {timeout} seconds")
            time.sleep(POLL_SECONDS)

    def _poll(self, handle: KubernetesRun, start_by: float) -> int | None:
        """The exit status of the task container if it has exited, None while it has not."""
        pod = self._pod(handle)
        if pod is None:
            job = self.api.read("job", handle.name)
            if job is None:
                if handle.stopped:
                    return 128 + signal.SIGTERM
                raise BackendError(f"The job {handle.name} is gone")
            failed = self._failed_condition(job)
            if failed is not None:
                raise BackendError(f"The job {handle.name} failed before it ran: {failed}")
            if time.monotonic() > start_by:
                raise BackendError(f"The job {handle.name} has no pod after {self.config.start_timeout} seconds")
            return None

        state, detail = _state(_status(pod, manifests.TASK_CONTAINER))
        phase = pod.get("status", {}).get("phase", "")
        if state == "terminated":
            return int(detail.get("exitCode", 1))
        if phase in ("Succeeded", "Failed"):
            if handle.stopped:
                return 128 + signal.SIGKILL
            raise BackendError(f"The pod {handle.pod} ended without a result: {_describe_pod(pod)}")
        if state == "waiting":
            reason = detail.get("reason", "")
            if reason in FATAL_WAITING:
                raise BackendError(f"The run's container cannot start: {reason}: {detail.get('message', '')}")
            if reason in IMAGE_PULL_ERRORS:
                handle.pulling_since = handle.pulling_since or time.monotonic()
                if time.monotonic() - handle.pulling_since > IMAGE_PULL_PATIENCE:
                    raise BackendError(f"Cannot pull the image of the run: {reason}: {detail.get('message', '')}")
            if time.monotonic() > start_by:
                raise BackendError(
                    f"The run's container did not start within {self.config.start_timeout} seconds: "
                    + _describe_pod(pod)
                )
        return None

    @staticmethod
    def _failed_condition(job: Mapping[str, Any]) -> str | None:
        for condition in job.get("status", {}).get("conditions") or []:
            if condition.get("type") == "Failed" and condition.get("status") == "True":
                return f"{condition.get('reason', 'Failed')}: {condition.get('message', '')}".rstrip(": ")
        return None

    def _join_forwarder(self, handle: KubernetesRun) -> None:
        handle.finished.set()
        if handle.forwarder is not None and handle.forwarder is not threading.current_thread():
            handle.forwarder.join(LOG_JOIN_SECONDS)

    @override
    def logs(self, handle: RunHandle, *, follow: bool = False) -> Iterator[str]:
        assert isinstance(handle, KubernetesRun)
        try:
            pod = self._pod(handle)
            if pod is None:
                raise BackendError(f"The run {handle.run_id} has no pod")
            yield from self.api.pod_log(handle.pod, manifests.TASK_CONTAINER, follow=follow)
        except KubeError as e:
            raise BackendError(f"Could not read the logs of {handle.name}: {e}") from e

    # ==================== results ====================

    @override
    def collect_results(self, handle: RunHandle, dest: Path) -> None:
        assert isinstance(handle, KubernetesRun)
        try:
            pod = self._pod(handle)
            if pod is None or _state(_status(pod, manifests.COLLECTOR_CONTAINER))[0] != "running":
                if handle.stopped:
                    logger.warning(f"The run {handle.run_id} was stopped before its results could be read")
                    return
                why = _describe_pod(pod) if pod else "the pod is gone"
                raise BackendError(f"The results of {handle.name} are no longer in the cluster: {why}")
            self._fetch(handle, manifests.COLLECTOR_RESULTS, dest)
            self._fetch(handle, manifests.COLLECTOR_ARCHIVE, dest / "archive")
        except KubeError as e:
            raise BackendError(f"Could not read the results of {handle.name}: {e}") from e
        self._release_collector(handle)

    def _fetch(self, handle: KubernetesRun, directory: str, dest: Path) -> None:
        with tempfile.TemporaryFile() as stream:
            try:
                _decode(
                    self.api.exec(
                        handle.pod, manifests.COLLECTOR_CONTAINER, ["sh", "-c", f"tar -cf - -C {directory} . | base64"]
                    ),
                    stream,
                )
            except binascii.Error as e:
                raise BackendError(f"The results of {handle.name} arrived damaged: {e}") from e
            _ = stream.seek(0)
            try:
                count = archive.unpack(stream, dest)
            except (archive.UnsafeArchiveError, OSError) as e:
                raise BackendError(f"Cannot unpack the results of {handle.name}: {e}") from e
            except Exception as e:  # tarfile.TarError: a truncated or damaged stream
                raise BackendError(f"The results of {handle.name} are not a valid archive: {e}") from e
        logger.info(f"Collected {count} files from {directory} of {handle.name}")

    def _release_collector(self, handle: KubernetesRun) -> None:
        """Let the collector exit, so the Job can finish."""
        try:
            _ = "".join(
                self.api.exec(handle.pod, manifests.COLLECTOR_CONTAINER, ["sh", "-c", f": > {manifests.DONE_FILE}"])
            )
        except KubeError as e:
            logger.debug(f"Could not release the collector of {handle.name}: {e}")

    # ==================== stopping ====================

    @override
    def stop(self, handle: RunHandle, grace: int = STOP_GRACE_SECONDS) -> None:
        assert isinstance(handle, KubernetesRun)
        handle.stopped = True
        try:
            pod = self._pod(handle)
            state = _state(_status(pod, manifests.TASK_CONTAINER))[0] if pod else "waiting"
            if pod is not None and state == "terminated":
                return
            if pod is None or state == "waiting":
                # Nothing runs yet, and there is nothing to keep.
                self.api.delete("job", handle.name, grace_seconds=0)
                return
            # The entrypoint is the container's first process and cleans up on SIGTERM, as it does under `docker stop`.
            _ = "".join(self.api.exec(handle.pod, manifests.TASK_CONTAINER, ["sh", "-c", "kill -TERM 1"]))
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                time.sleep(min(POLL_SECONDS, 0.5))
                pod = self._pod(handle)
                if pod is None or _state(_status(pod, manifests.TASK_CONTAINER))[0] == "terminated":
                    return
            # A process cannot SIGKILL the first process of its container, so the pod goes, and its results with it.
            logger.warning(f"{handle.name} did not stop within {grace} seconds; deleting it")
            self.api.delete("job", handle.name, grace_seconds=0)
        except KubeError as e:
            logger.warning(f"Could not stop {handle.name}: {e}")

    @override
    def cleanup(self, handle: RunHandle) -> None:
        assert isinstance(handle, KubernetesRun)
        self._join_forwarder(handle)
        if handle.keep:
            try:
                pod = self._pod(handle)
                if pod is not None and _state(_status(pod, manifests.COLLECTOR_CONTAINER))[0] == "running":
                    self._release_collector(handle)
            except KubeError as e:
                logger.debug(f"Could not release the collector of {handle.name}: {e}")
            logger.info(
                f"Kept the job {handle.name}; remove it with "
                f"`kubectl delete job,secret,networkpolicy -n {self.api.namespace} -l {RUN_ID_LABEL}={handle.run_id}`"
            )
            return
        self._remove(handle.name)
        if handle.pod:
            forward.stop_forwards(self.api.namespace, handle.pod)

    # ==================== reaching a run ====================

    def _running_pod(self, handle: RunHandle) -> str:
        assert isinstance(handle, KubernetesRun)
        try:
            pod = self._pod(handle)
        except KubeError as e:
            raise BackendError(f"Could not find the pod of {handle.name}: {e}") from e
        if pod is None or _state(_status(pod, manifests.TASK_CONTAINER))[0] != "running":
            raise BackendError(f"The run {handle.run_id} is not running")
        return handle.pod

    @override
    def endpoint(self, handle: RunHandle, port: int) -> str:
        """A `kubectl port-forward` to the pod on a port of 127.0.0.1, which outlives this process and is reused.

        The run's network policy admits no ingress, so a Service or a pod address would not reach the run
        from anywhere; a forward goes through the API server and the kubelet, which the policy does not
        cover. It needs `kubectl` and the `pods/portforward` permission. It ends when the pod does, or
        when the run is removed.
        """
        pod = self._running_pod(handle)
        local = forward.forward(self.api.namespace, self.config.context, pod, port)
        return f"http://127.0.0.1:{local}"

    @override
    def exec_argv(
        self,
        handle: RunHandle,
        command: Sequence[str],
        *,
        user: str | None = None,
        workdir: str | None = None,
        tty: bool = False,
        stdin: bool = False,
        env_names: Sequence[str] = (),
    ) -> list[str]:
        if env_names:
            # `kubectl exec` has no option that takes a value from the environment, and putting it in the
            # vector would show it in the process list.
            raise BackendError("The kubernetes backend cannot pass environment variables to a command")
        pod = self._running_pod(handle)
        inner = list(command)
        if workdir or user:
            script = f"cd {shlex.quote(workdir)} && " if workdir else ""
            script += "exec " + shlex.join(command)
            inner = ["sh", "-c", script]
            if user:
                inner = ["su", "-s", "/bin/sh", user, "-c", shlex.join(inner)]
        return [
            *forward.kubectl_base(self.api.namespace, self.config.context),
            "exec",
            *(["--stdin"] if stdin or tty else []),
            *(["--tty"] if tty else []),
            "--container",
            manifests.TASK_CONTAINER,
            pod,
            "--",
            *inner,
        ]

    # ==================== finding runs ====================

    @override
    def list_runs(self, labels: Mapping[str, str] | None = None) -> list[RunInfo]:
        wanted = dict(labels or {})
        selector = [f"{manifests.MANAGED_BY[0]}={manifests.MANAGED_BY[1]}"]
        # A label value that Kubernetes cannot hold is kept as an annotation, so it is matched here.
        client_side = {key: value for key, value in wanted.items() if not manifests.label_value(value)}
        selector += [f"{key}={value}" for key, value in wanted.items() if key not in client_side]
        try:
            jobs = self.api.find("job", ",".join(selector))
            pods = self.api.find("pod", ",".join(selector))
        except KubeError as e:
            raise BackendError(f"Could not list the runs: {e}") from e
        by_job: dict[str, list[dict[str, Any]]] = {}
        for pod in pods:
            by_job.setdefault(pod["metadata"].get("labels", {}).get("job-name", ""), []).append(pod)
        runs: list[RunInfo] = []
        for job in jobs:
            meta = job["metadata"]
            annotations = meta.get("annotations") or {}
            if any(annotations.get(key) != value for key, value in client_side.items()):
                continue
            newest = max(
                by_job.get(meta["name"], []), key=lambda p: p["metadata"].get("creationTimestamp", ""), default=None
            )
            runs.append(self._info(job, newest))
        return runs

    @staticmethod
    def _info(job: Mapping[str, Any], pod: Mapping[str, Any] | None) -> RunInfo:
        meta = job["metadata"]
        labels = {**(meta.get("annotations") or {}), **(meta.get("labels") or {})}
        run_id = labels.get(RUN_ID_LABEL, "")
        state: RunState = "created"
        exit_code: int | None = None
        if pod is not None:
            kind, detail = _state(_status(pod, manifests.TASK_CONTAINER))
            if kind == "running":
                state = "running"
            elif kind == "terminated":
                state, exit_code = "exited", int(detail.get("exitCode", 1))
            elif pod.get("status", {}).get("phase") in ("Succeeded", "Failed"):
                state = "exited"
        elif KubernetesBackend._failed_condition(job) is not None:
            state = "exited"
        containers = job["spec"]["template"]["spec"]["containers"]
        image = next((c["image"] for c in containers if c["name"] == manifests.TASK_CONTAINER), "")
        handle = KubernetesRun(
            run_id=run_id,
            name=meta["name"],
            pod=pod["metadata"]["name"] if pod else "",
        )
        return RunInfo(
            run_id=run_id,
            created_at=meta.get("creationTimestamp"),
            name=meta["name"],
            state=state,
            exit_code=exit_code,
            image=image,
            labels=labels,
            handle=handle,
        )
