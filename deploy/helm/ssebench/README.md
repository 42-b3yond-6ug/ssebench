# SSEBench Helm chart

Installs the SSEBench stack on Kubernetes: the LiteLLM proxy with its Postgres, the task
catalog, and the web UI on the Kubernetes backend, with the RBAC that lets the web UI
create runs as Jobs.

```sh
helm install ssebench oci://ghcr.io/42-b3yond-6ug/ssebench/charts/ssebench \
  --version <version> --namespace ssebench --create-namespace \
  --set litellm.providerKeySecrets={provider-keys} --set runs.namespace=ssebench-runs
```

The cluster needs a network plugin that enforces NetworkPolicy, and the runs' namespace
must exist. The web UI is a read-only viewer unless you set `webui.hosted=false`.

[values.yaml](values.yaml) lists every value; the
[Kubernetes deployment guide](../../../docs/deployment/kubernetes.md) describes them,
what the chart installs and its security notes. `ci/` holds the value files that the
chart's CI lints.
