# deploy

Deployment configurations.

| Path | What it is |
|---|---|
| [`compose/docker-compose.yaml`](compose/docker-compose.yaml) | The LiteLLM proxy and its Postgres database. `just launch` and `ssebench run` start it; its names are scoped to the Compose project `COMPOSE_PROJECT_NAME`. |
| [`compose/demo.yaml`](compose/demo.yaml) | Adds the task catalog and the web UI, for `just demo`. |
| [`helm/ssebench`](helm/ssebench) | The Helm chart: the LiteLLM proxy with Postgres, the catalog, the web UI on the Kubernetes backend, and the RBAC. |
| [`k8s/rbac.yaml`](k8s/rbac.yaml) | The service account and the minimal namespaced `Role` for `ssebench run --backend kubernetes`. |
| [`k8s/litellm-test.yaml`](k8s/litellm-test.yaml) | A throwaway LiteLLM proxy and Postgres with fake keys, for trying the Kubernetes backend. |
| [`k8s/kind.yaml`](k8s/kind.yaml) | A kind cluster without the default network plugin, which does not enforce NetworkPolicy; install Calico on it. |

The CLI drives the Compose files; you rarely call `docker compose` yourself. The web UI
container in the demo mounts the Docker socket, which is root access to the host:
read [Web UI security](../docs/webui/security.md) before you run it anywhere but
your own machine.

- [Local stack](../docs/deployment/compose.md)
- [Try the demo](../docs/getting-started/demo.md)
- [Kubernetes and the Helm chart](../docs/deployment/kubernetes.md)
