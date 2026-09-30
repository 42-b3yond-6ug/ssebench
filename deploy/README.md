# deploy

Deployment configurations.

| Path | What it is |
|---|---|
| [`compose/docker-compose.yaml`](compose/docker-compose.yaml) | The LiteLLM proxy and its Postgres database. `just launch` and `ssebench run` start it; its names are scoped to the Compose project `COMPOSE_PROJECT_NAME`. |
| [`compose/demo.yaml`](compose/demo.yaml) | Adds the task catalog and the web UI, for `just demo`. |

The CLI drives both files; you rarely call `docker compose` yourself. The web UI
container in the demo mounts the Docker socket, which is root access to the host:
read [Web UI security](../docs/webui/security.md) before you run it anywhere but
your own machine.

- [Local stack](../docs/deployment/compose.md)
- [Try the demo](../docs/getting-started/demo.md)
- [Kubernetes](../docs/deployment/kubernetes.md)
