"""Settings of the Kubernetes backend: where the runs go and what they get."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import urlsplit

import yaml

from ssebench import settings, stack
from ssebench.errors import UserError

NAMESPACE_FILE: Final = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
PROXY_SERVICE: Final = "litellm"
PROXY_PORT: Final = 4000
DEFAULT_PROXY_SELECTOR: Final[Mapping[str, str]] = MappingProxyType({"app.kubernetes.io/name": "litellm"})

DEFAULT_RESOURCES: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "requests": MappingProxyType({"cpu": "1", "memory": "2Gi", "ephemeral-storage": "2Gi"}),
        "limits": MappingProxyType({"cpu": "4", "memory": "8Gi", "ephemeral-storage": "20Gi"}),
    }
)
"""What the task container gets unless `SSEBENCH_K8S_RESOURCES` says otherwise. The request is what a small task
needs to build and test; the limits are ceilings for the largest builds."""

# The capabilities of the task container. Its entrypoint runs as root and must become the agent's and the
# task scripts' users (SETUID, SETGID), hand them their directories (CHOWN, FOWNER), read what they own
# (DAC_OVERRIDE) and kill their leftover processes after a check (KILL). It needs nothing else.
CAPABILITIES: Final = ("CHOWN", "DAC_OVERRIDE", "FOWNER", "KILL", "SETGID", "SETUID")


class KubernetesConfigError(UserError):
    """A setting of the Kubernetes backend is malformed."""


def _list(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _positive(name: str, default: int) -> int:
    raw = settings.get(name)
    if not raw:
        return default
    if not raw.isdigit() or int(raw) == 0:
        raise KubernetesConfigError(f"{name}={raw!r} is not a positive number of seconds")
    return int(raw)


def _selector(raw: str) -> Mapping[str, str]:
    """`key=value,key=value` as a mapping."""
    selector: dict[str, str] = {}
    for item in _list(raw):
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise KubernetesConfigError(f"SSEBENCH_K8S_PROXY_SELECTOR: {item!r} is not key=value")
        selector[key.strip()] = value.strip()
    return selector


def _resources(raw: str) -> Mapping[str, Mapping[str, str]]:
    if not raw:
        return DEFAULT_RESOURCES
    try:
        parsed: Any = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise KubernetesConfigError(f"SSEBENCH_K8S_RESOURCES is not JSON or YAML: {e}") from e
    if not isinstance(parsed, dict) or not set(parsed) <= {"requests", "limits"}:
        raise KubernetesConfigError("SSEBENCH_K8S_RESOURCES must be a mapping with `requests` and `limits`")
    resources: dict[str, Mapping[str, str]] = {}
    for section in ("requests", "limits"):
        values: Any = parsed.get(section, {})
        if not isinstance(values, dict):
            raise KubernetesConfigError(f"SSEBENCH_K8S_RESOURCES: `{section}` must be a mapping")
        resources[section] = {str(name): str(quantity) for name, quantity in values.items()}
    return resources


@dataclass(frozen=True, kw_only=True)
class KubernetesConfig:
    """Where a run's Job goes, how it reaches the proxy, and what it may use.

    An empty `namespace` is the namespace of the kubeconfig context, or of the pod the runner is in.
    """

    namespace: str = ""
    context: str | None = None
    proxy_service_url: str | None = None
    """The proxy as the run's pod reaches it; the default is the `litellm` Service of `proxy_namespace`."""
    proxy_host_url: str | None = None
    """The proxy as the runner reaches it: in a cluster the same Service, else `localhost` on `LITELLM_PORT`
    (a port-forward)."""
    proxy_namespace: str = ""
    proxy_selector: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_PROXY_SELECTOR))
    """Labels of the proxy's pods, which the restricted network policy lets a run reach."""
    runtime_class: str | None = None
    image_pull_policy: str = "IfNotPresent"
    image_pull_secrets: tuple[str, ...] = ()
    resources: Mapping[str, Mapping[str, str]] = field(default_factory=lambda: dict(DEFAULT_RESOURCES))
    ttl_seconds: int = 3600
    """How long a finished Job, its pod and its logs stay, before the cluster removes them."""
    deadline_slack: int = 1800
    """Seconds on top of the agent's timeout before the cluster stops the Job: image pulls, the build and grading."""
    start_timeout: int = 600
    """Seconds a run's container may take to start before the run fails."""
    capabilities: tuple[str, ...] = CAPABILITIES

    @classmethod
    def from_settings(cls) -> "KubernetesConfig":
        """The configuration that the `SSEBENCH_K8S_*` settings describe."""
        return cls(
            namespace=settings.get("SSEBENCH_K8S_NAMESPACE"),
            context=settings.get("SSEBENCH_K8S_CONTEXT") or None,
            proxy_service_url=settings.get("SSEBENCH_K8S_PROXY_URL") or None,
            proxy_host_url=settings.get("SSEBENCH_K8S_PROXY_HOST_URL") or None,
            proxy_namespace=settings.get("SSEBENCH_K8S_PROXY_NAMESPACE"),
            proxy_selector=_selector(settings.get("SSEBENCH_K8S_PROXY_SELECTOR")) or dict(DEFAULT_PROXY_SELECTOR),
            runtime_class=settings.get("SSEBENCH_K8S_RUNTIME_CLASS") or None,
            image_pull_policy=settings.get("SSEBENCH_K8S_IMAGE_PULL_POLICY", "IfNotPresent"),
            image_pull_secrets=_list(settings.get("SSEBENCH_K8S_IMAGE_PULL_SECRETS")),
            resources=_resources(settings.get("SSEBENCH_K8S_RESOURCES")),
            ttl_seconds=_positive("SSEBENCH_K8S_TTL_SECONDS", 3600),
            deadline_slack=_positive("SSEBENCH_K8S_DEADLINE_SLACK", 1800),
        )


def in_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


def service_url(config: KubernetesConfig, namespace: str) -> str:
    """The URL a run's pod uses for the proxy."""
    return config.proxy_service_url or f"http://{PROXY_SERVICE}.{config.proxy_namespace or namespace}.svc:{PROXY_PORT}"


def host_url(config: KubernetesConfig, namespace: str) -> str:
    """The URL the runner uses for the proxy: the Service from inside a cluster, a port-forward otherwise."""
    if config.proxy_host_url:
        return config.proxy_host_url
    return service_url(config, namespace) if in_cluster() else stack.host_url()


def proxy_port(url: str) -> int:
    """The port of the proxy's URL, for the network policy."""
    parts = urlsplit(url)
    if parts.port is not None:
        return parts.port
    return 443 if parts.scheme == "https" else 80
