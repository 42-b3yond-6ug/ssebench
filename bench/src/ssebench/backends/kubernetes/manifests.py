"""The Kubernetes objects of a run, as the plain dictionaries the API accepts.

A run is one Job with one pod, a Secret with the pod's environment and files, and a NetworkPolicy for the
pod. Nothing here talks to a cluster, so the objects are checked by comparing dictionaries.

The pod has two containers of the same image that share the run's results and archive volumes:

- `task` runs the image as it is. It is the container the run waits for.
- `collector` only waits. The results are files in the pod's volumes, so once `task` has exited, something has
  to be running in the pod for the backend to read them out. The backend tells it to exit afterwards.
"""

import base64
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from ssebench.backends.base import (
    ARCHIVE_PATH,
    RESULTS_PATH,
    RUN_ID_LABEL,
    Mount,
    RunSpec,
)
from ssebench.backends.kubernetes.config import KubernetesConfig, proxy_port

MANAGED_BY: Final = ("app.kubernetes.io/managed-by", "ssebench")
NAME_LABEL: Final = ("app.kubernetes.io/name", "ssebench-run")
TASK_CONTAINER: Final = "task"
COLLECTOR_CONTAINER: Final = "collector"
COLLECTOR_RESULTS: Final = "/results"
COLLECTOR_ARCHIVE: Final = "/archive"
CONTROL_DIR: Final = "/control"
"""The collector's own volume: it exits once `done` exists there."""
DONE_FILE: Final = f"{CONTROL_DIR}/done"

TERMINATION_GRACE_SECONDS: Final = 30
"""How long the entrypoint has to clean up when the pod is deleted; it needs a few seconds."""
VOLUME_SIZE_LIMIT: Final = "2Gi"
MAX_ARTIFACT_BYTES: Final = 512 * 1024
"""A Secret holds 1 MiB in all; the reference patch is far smaller."""

# Private and link-local ranges that a run with open egress must not reach: the cluster's own pods and
# services, the nodes and the cloud metadata service.
PRIVATE_RANGES: Final = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "169.254.0.0/16",
)

_LABEL_VALUE = re.compile(r"(?:[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?)?")
_NAME_PREFIX = "ssebench-"
_NAME_MAX = 63 - len("-xxxxxxxx")


def object_name(run_id: str) -> str:
    """A DNS label for the run's Job, Secret and NetworkPolicy; the run ID itself is in the labels."""
    slug = re.sub(r"[^a-z0-9-]+", "-", run_id.lower()).strip("-")
    name = _NAME_PREFIX + slug
    if name == _NAME_PREFIX + run_id and len(name) <= 63:
        return name
    digest = hashlib.sha256(run_id.encode()).hexdigest()[:8]
    return f"{name[:_NAME_MAX].rstrip('-')}-{digest}"


def label_value(value: str) -> bool:
    return len(value) <= 63 and _LABEL_VALUE.fullmatch(value) is not None


def run_labels(spec: RunSpec) -> dict[str, str]:
    """The labels of the run's objects: the runner's labels that Kubernetes accepts, and the run's ID."""
    labels = {key: value for key, value in spec.labels.items() if label_value(value)}
    labels[RUN_ID_LABEL] = spec.run_id
    labels[MANAGED_BY[0]] = MANAGED_BY[1]
    labels[NAME_LABEL[0]] = NAME_LABEL[1]
    return labels


def run_annotations(spec: RunSpec) -> dict[str, str]:
    """Every label of the runner, whole: a value such as the run directory's path is not a valid label value."""
    return {**spec.labels, RUN_ID_LABEL: spec.run_id}


def metadata(name: str, labels: Mapping[str, str], annotations: Mapping[str, str] | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"name": name, "labels": dict(labels)}
    if annotations:
        meta["annotations"] = dict(annotations)
    return meta


def artifact_key(index: int) -> str:
    return f"artifact-{index}"


def read_artifacts(mounts: tuple[Mount, ...]) -> dict[str, bytes]:
    """The content of the runner's files, by Secret key. Raises OSError if one cannot be read or is too large."""
    content: dict[str, bytes] = {}
    for index, mount in enumerate(mounts):
        data = Path(mount.source).read_bytes()
        if len(data) > MAX_ARTIFACT_BYTES:
            raise OSError(f"{mount.source} is {len(data)} bytes; a file for the container can be {MAX_ARTIFACT_BYTES}")
        content[artifact_key(index)] = data
    return content


def secret(spec: RunSpec, name: str, artifacts: Mapping[str, bytes]) -> dict[str, Any]:
    """The run's environment, which holds its model key, and the content of its files."""
    data = {key: base64.b64encode(value.encode()).decode() for key, value in spec.env.items()}
    data.update({key: base64.b64encode(value).decode() for key, value in artifacts.items()})
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": metadata(name, run_labels(spec), run_annotations(spec)),
        "type": "Opaque",
        "data": data,
    }


def _security_context(capabilities: tuple[str, ...]) -> dict[str, Any]:
    """Root without the rest of root: the container may do what the entrypoint needs and nothing more."""
    return {
        "privileged": False,
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": False,
        "runAsUser": 0,
        "runAsNonRoot": False,
        "capabilities": {"drop": ["ALL"], "add": list(capabilities)},
    }


def _collector_command(seconds: int) -> list[str]:
    """Wait until `DONE_FILE` exists, or for `seconds`, whichever comes first."""
    script = f'i=0; while [ ! -e {DONE_FILE} ] && [ "$i" -lt {seconds} ]; do sleep 1; i=$((i+1)); done'
    return ["sh", "-c", script]


def job(spec: RunSpec, config: KubernetesConfig, name: str, artifacts: Mapping[str, bytes]) -> dict[str, Any]:
    """The Job that runs `spec`: one pod, no retries, a deadline and, unless the run is kept, a time to live."""
    labels = run_labels(spec)
    annotations = run_annotations(spec)
    deadline = spec.timeout + config.deadline_slack

    volumes: list[dict[str, Any]] = [
        {"name": "results", "emptyDir": {"sizeLimit": VOLUME_SIZE_LIMIT}},
        {"name": "archive", "emptyDir": {"sizeLimit": VOLUME_SIZE_LIMIT}},
        {"name": "control", "emptyDir": {"sizeLimit": "1Mi"}},
    ]
    task_mounts: list[dict[str, Any]] = [
        {"name": "results", "mountPath": RESULTS_PATH},
        {"name": "archive", "mountPath": ARCHIVE_PATH},
    ]
    if artifacts:
        volumes.append(
            {
                "name": "files",
                "secret": {
                    "secretName": name,
                    "defaultMode": 0o444,
                    "items": [{"key": key, "path": key} for key in artifacts],
                },
            }
        )
        task_mounts += [
            {"name": "files", "mountPath": mount.target, "subPath": artifact_key(index), "readOnly": True}
            for index, mount in enumerate(spec.artifacts)
        ]

    task: dict[str, Any] = {
        "name": TASK_CONTAINER,
        "image": spec.image,
        "imagePullPolicy": config.image_pull_policy,
        "envFrom": [{"secretRef": {"name": name}}],
        "resources": {key: dict(value) for key, value in config.resources.items()},
        "securityContext": _security_context(config.capabilities),
        "volumeMounts": task_mounts,
    }
    collector: dict[str, Any] = {
        "name": COLLECTOR_CONTAINER,
        "image": spec.image,
        "imagePullPolicy": config.image_pull_policy,
        "command": _collector_command(deadline),
        "resources": {
            "requests": {"cpu": "10m", "memory": "16Mi"},
            "limits": {"cpu": "200m", "memory": "256Mi"},
        },
        # Root, to read the task's root-only results and the agent's archive; it changes nothing.
        "securityContext": {
            "privileged": False,
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsUser": 0,
            "runAsNonRoot": False,
            "capabilities": {"drop": ["ALL"], "add": ["DAC_READ_SEARCH"]},
        },
        "volumeMounts": [
            {"name": "results", "mountPath": COLLECTOR_RESULTS, "readOnly": True},
            {"name": "archive", "mountPath": COLLECTOR_ARCHIVE, "readOnly": True},
            {"name": "control", "mountPath": CONTROL_DIR},
        ],
    }

    pod_spec: dict[str, Any] = {
        "restartPolicy": "Never",
        "terminationGracePeriodSeconds": TERMINATION_GRACE_SECONDS,
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "hostNetwork": False,
        "hostPID": False,
        "hostIPC": False,
        "shareProcessNamespace": False,
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [task, collector],
        "volumes": volumes,
    }
    if config.runtime_class:
        pod_spec["runtimeClassName"] = config.runtime_class
    if config.image_pull_secrets:
        pod_spec["imagePullSecrets"] = [{"name": secret_name} for secret_name in config.image_pull_secrets]

    job_spec: dict[str, Any] = {
        "backoffLimit": 0,
        "completions": 1,
        "parallelism": 1,
        "activeDeadlineSeconds": deadline,
        "template": {"metadata": {"labels": labels, "annotations": annotations}, "spec": pod_spec},
    }
    if not spec.keep:
        job_spec["ttlSecondsAfterFinished"] = config.ttl_seconds
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": metadata(name, labels, annotations),
        "spec": job_spec,
    }


def network_policy(
    spec: RunSpec, config: KubernetesConfig, name: str, namespace: str, proxy_url: str
) -> dict[str, Any]:
    """What the run's pod may reach, and nothing may reach it.

    `restricted` allows the cluster's DNS and the model proxy. `open` adds the internet, but not the private
    ranges that hold the cluster and its nodes. The proxy is allowed on both, since the pod's environment names it.
    """
    dns = {
        "to": [
            {
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
            }
        ],
        "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}],
    }
    proxy = {
        "to": [
            {
                "namespaceSelector": {
                    "matchLabels": {"kubernetes.io/metadata.name": config.proxy_namespace or namespace}
                },
                "podSelector": {"matchLabels": dict(config.proxy_selector)},
            }
        ],
        "ports": [{"protocol": "TCP", "port": proxy_port(proxy_url)}],
    }
    egress = [dns, proxy]
    if spec.network.egress == "open":
        egress.append({"to": [{"ipBlock": {"cidr": "0.0.0.0/0", "except": list(PRIVATE_RANGES)}}]})
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": metadata(name, run_labels(spec), run_annotations(spec)),
        "spec": {
            "podSelector": {"matchLabels": {RUN_ID_LABEL: spec.run_id}},
            # Listing Ingress with no ingress rule denies all of it: one run cannot reach another's daemon.
            "policyTypes": ["Ingress", "Egress"],
            "egress": egress,
        },
    }


def copy_pod(image: str, path: str, name: str, config: KubernetesConfig) -> dict[str, Any]:
    """A pod that prints one file of `image` as base64, for the reference patch."""
    labels = {MANAGED_BY[0]: MANAGED_BY[1], "ssebench.copy": "true"}
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": metadata(name, labels),
        "spec": {
            "restartPolicy": "Never",
            "activeDeadlineSeconds": 300,
            "automountServiceAccountToken": False,
            "enableServiceLinks": False,
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            **({"runtimeClassName": config.runtime_class} if config.runtime_class else {}),
            **(
                {"imagePullSecrets": [{"name": secret_name} for secret_name in config.image_pull_secrets]}
                if config.image_pull_secrets
                else {}
            ),
            "containers": [
                {
                    "name": "copy",
                    "image": image,
                    "imagePullPolicy": config.image_pull_policy,
                    "command": ["sh", "-c", 'base64 "$0"', path],
                    "securityContext": {
                        "privileged": False,
                        "allowPrivilegeEscalation": False,
                        "runAsUser": 0,
                        "runAsNonRoot": False,
                        "capabilities": {"drop": ["ALL"], "add": ["DAC_READ_SEARCH"]},
                    },
                }
            ],
        },
    }
