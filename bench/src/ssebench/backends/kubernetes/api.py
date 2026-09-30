"""The few Kubernetes API calls the backend makes, behind one interface.

Objects are plain dictionaries in the API's own (camelCase) form. The backend depends on `KubeApi` only, so
its tests use an in-memory cluster; `KubeClient` is the implementation on the official `kubernetes` client,
which is an optional dependency (`pip install 'ssebench[kubernetes]'`) and imported when a client is made.
"""

import http.client
import json
import logging
from collections.abc import Iterator, Mapping
from typing import Any, Final, Literal, Protocol

logger = logging.getLogger(__name__)

Kind = Literal["job", "pod", "secret", "networkpolicy"]

INSTALL_HINT: Final = "The Kubernetes backend needs the kubernetes client: pip install 'ssebench[kubernetes]'"


class KubeError(RuntimeError):
    """A call to the Kubernetes API failed. The message is the API's own and carries no object content."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class KubeApi(Protocol):
    """What the backend needs from a cluster, in one namespace."""

    namespace: str

    def create(self, kind: Kind, body: Mapping[str, Any]) -> dict[str, Any]:
        """Create an object. A name that is taken raises `KubeError` with status 409."""
        ...

    def read(self, kind: Kind, name: str) -> dict[str, Any] | None:
        """The object, or None if it does not exist."""
        ...

    def find(self, kind: Kind, label_selector: str = "") -> list[dict[str, Any]]:
        """The objects that match `label_selector`, in the API's list order."""
        ...

    def patch(self, kind: Kind, name: str, body: Mapping[str, Any]) -> None:
        """Merge `body` into the object."""
        ...

    def delete(self, kind: Kind, name: str, *, grace_seconds: int | None = None) -> None:
        """Delete the object, with its dependents in the background; one that does not exist is not an error."""
        ...

    def pod_log(
        self,
        pod: str,
        container: str,
        *,
        follow: bool = False,
        timestamps: bool = False,
        since_seconds: int | None = None,
    ) -> Iterator[str]:
        """The lines of a container's output, without their line ends. With `timestamps`, each line starts with
        an RFC 3339 timestamp and a space. `since_seconds` skips what is older than that."""
        ...

    def exec(self, pod: str, container: str, command: list[str]) -> Iterator[str]:
        """Run `command` in a container and yield its standard output as text as it arrives.

        Raises `KubeError` when the command exits with a status other than 0.
        """
        ...


def _message(e: Exception) -> str:
    """The API's message of a failed call. The body is parsed rather than passed on whole."""
    body = getattr(e, "body", None)
    if body:
        try:
            parsed = json.loads(body)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict) and parsed.get("message"):
            return str(parsed["message"])
    return str(getattr(e, "reason", "") or e.__class__.__name__)


class KubeClient:
    """`KubeApi` on the official Python client, with a kubeconfig or the pod's own service account."""

    def __init__(self, namespace: str = "", context: str | None = None) -> None:
        try:
            from kubernetes import client, config
        except ImportError as e:
            raise KubeError(INSTALL_HINT) from e
        try:
            config.load_kube_config(context=context)
            _, active = config.list_kube_config_contexts()
            configured = ((active or {}).get("context") or {}).get("namespace", "")
        except config.ConfigException:
            try:
                config.load_incluster_config()
            except config.ConfigException as e:
                raise KubeError(f"No Kubernetes cluster to use: no kubeconfig, and not in a cluster ({e})") from e
            configured = self._pod_namespace()
        self._client = client
        self._batch = client.BatchV1Api()
        self._core = client.CoreV1Api()
        self._networking = client.NetworkingV1Api()
        self.namespace = namespace or configured or "default"

    @staticmethod
    def _pod_namespace() -> str:
        from ssebench.backends.kubernetes.config import NAMESPACE_FILE

        try:
            with open(NAMESPACE_FILE) as f:
                return f.read().strip()
        except OSError:
            return ""

    def _api(self, kind: Kind) -> tuple[Any, str]:
        """The client and the suffix of its calls for `kind`."""
        match kind:
            case "job":
                return self._batch, "namespaced_job"
            case "pod":
                return self._core, "namespaced_pod"
            case "secret":
                return self._core, "namespaced_secret"
            case "networkpolicy":
                return self._networking, "namespaced_network_policy"

    def _call(self, kind: Kind, verb: str, *args: Any, **kwargs: Any) -> Any:
        api, suffix = self._api(kind)
        try:
            return getattr(api, f"{verb}_{suffix}")(*args, **kwargs)
        except self._client.ApiException as e:
            raise KubeError(f"{verb} {kind} failed: {_message(e)}", e.status) from e
        except (OSError, http.client.HTTPException) as e:
            raise KubeError(f"{verb} {kind} failed: {e}") from e

    def _dict(self, obj: Any) -> dict[str, Any]:
        result: Any = self._client.ApiClient().sanitize_for_serialization(obj)
        return dict(result)

    def create(self, kind: Kind, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._dict(self._call(kind, "create", self.namespace, dict(body)))

    def read(self, kind: Kind, name: str) -> dict[str, Any] | None:
        try:
            return self._dict(self._call(kind, "read", name, self.namespace))
        except KubeError as e:
            if e.status == 404:
                return None
            raise

    def find(self, kind: Kind, label_selector: str = "") -> list[dict[str, Any]]:
        result = self._dict(self._call(kind, "list", self.namespace, label_selector=label_selector))
        return list(result.get("items") or [])

    def patch(self, kind: Kind, name: str, body: Mapping[str, Any]) -> None:
        _ = self._call(kind, "patch", name, self.namespace, dict(body))

    def delete(self, kind: Kind, name: str, *, grace_seconds: int | None = None) -> None:
        options: dict[str, Any] = {"propagation_policy": "Background"}
        if grace_seconds is not None:
            options["grace_period_seconds"] = grace_seconds
        try:
            _ = self._call(kind, "delete", name, self.namespace, **options)
        except KubeError as e:
            if e.status != 404:
                raise

    def pod_log(
        self,
        pod: str,
        container: str,
        *,
        follow: bool = False,
        timestamps: bool = False,
        since_seconds: int | None = None,
    ) -> Iterator[str]:
        options: dict[str, Any] = {"container": container, "follow": follow, "timestamps": timestamps}
        if since_seconds:
            options["since_seconds"] = since_seconds
        try:
            response: Any = self._core.read_namespaced_pod_log(pod, self.namespace, _preload_content=False, **options)
        except self._client.ApiException as e:
            raise KubeError(f"reading the log of {pod} failed: {_message(e)}", e.status) from e
        pending = b""
        try:
            for chunk in response.stream(8192):
                pending += chunk
                *lines, pending = pending.split(b"\n")
                for line in lines:
                    yield line.decode(errors="replace")
            if pending:
                yield pending.decode(errors="replace")
        except (OSError, http.client.HTTPException) as e:
            raise KubeError(f"reading the log of {pod} failed: {e}") from e
        finally:
            response.release_conn()

    def exec(self, pod: str, container: str, command: list[str]) -> Iterator[str]:
        from kubernetes.stream import stream

        try:
            channel = stream(
                self._core.connect_get_namespaced_pod_exec,
                pod,
                self.namespace,
                container=container,
                command=command,
                stdin=False,
                stdout=True,
                stderr=True,
                tty=False,
                _preload_content=False,
            )
        except self._client.ApiException as e:
            raise KubeError(f"exec in {pod} failed: {_message(e)}", e.status) from e
        errors = ""
        try:
            while channel.is_open():
                channel.update(timeout=1)
                if channel.peek_stdout():
                    yield channel.read_stdout()
                if channel.peek_stderr():
                    errors = (errors + channel.read_stderr())[-2000:]
            while channel.peek_stdout():
                yield channel.read_stdout()
            status = channel.returncode
        finally:
            channel.close()
        if status != 0:
            raise KubeError(f"`{' '.join(command[:3])}` in {pod} exited with status {status}: {errors.strip()}")
