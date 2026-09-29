---
outline: deep
---

# Integrity and egress

This page covers the settings outside the task container that affect benchmark
integrity: the network a run container joins, and how to run several runs on
one host without them seeing each other's answers. The
[integrity model](/concepts/integrity) describes the protections inside the
container.

It applies to the local Docker setup. The [Kubernetes](/deployment/kubernetes)
deployment is not available yet.

## Networks

The [LiteLLM proxy](/concepts/litellm-proxy)'s Compose project defines two
networks, both named after the project (`COMPOSE_PROJECT_NAME`, default
`ssebench`):

| Network | Kind | Members |
|---|---|---|
| `<project>_default` | normal bridge, with internet access | the proxy, its database, and run containers with `--egress open` |
| `<project>_agents` | `internal: true`: no route out of the host | the proxy, and run containers with `--egress restricted` (the default) |

```
                     internet
                        ^
                        |
      <project>_default | (bridge)
   +--------------------+----------------------+
   |  litellm_db     litellm        open runs  |
   +-------------------+-----------------------+
                       |
      <project>_agents | (internal)
   +-------------------+-----------------------+
   |               litellm    restricted runs  |
   +-------------------------------------------+
```

The proxy is on both, as `litellm`, so `SSE_BASE_URL=http://litellm:4000`
works on either. The database is on the default network only. The networks
exist while the stack is up; `ssebench run` starts the stack before every run.

## Egress policies

`ssebench run --egress POLICY` chooses the network. The run summary records
the choice as `config.egress`.

### `restricted` (default)

The run container joins `<project>_agents`. From there it reaches:

- the LiteLLM proxy, at `litellm:4000`;
- other containers on the same network: the other run containers of the
  project.

It does not reach the internet, and names outside Docker do not resolve. So
the agent cannot clone the upstream repository, read the advisory or the fix
commit, or download packages while it works. Everything a task needs to build
and test must be in its case image, and everything an agent needs when it
starts must be in its agent image.

### `open`

The run container joins `<project>_default`, the normal bridge with internet
access that the proxy is also on. Use it only for tasks that need the network
at test time. The agent can then reach the upstream project, its history and its
fix, so results from open runs are not comparable with restricted ones; filter
on `config.egress` when you aggregate results.

### What the restricted policy does not cover

- **Requests through the proxy.** The proxy forwards the agent's requests to
  the model provider. A provider-hosted tool that a request turns on, such as
  web search, runs at the provider, outside this network. The per-run key
  limits which model the agent may use and how much it may spend, not which
  features of the provider's API it uses.
- **Other runs.** Run containers of one Compose project share
  `<project>_agents` and can connect to each other. The daemon's HTTP port,
  4263, listens on all interfaces, and after a run's agent phase ends it
  serves that run's reference patch; so do containers kept with
  `--keep-container`, for as long as they run. Do not keep finished containers
  of a task while other runs of the same task are in progress, or use a
  separate Compose project for each experiment, as below.
- **The host's kernel.** The network policy does nothing against an escape
  from the container itself.

## Running experiments side by side

Each Compose project has its own proxy, database and networks. To keep
experiments apart, give each one its own project and port, in the environment
or in `.env`:

```sh
COMPOSE_PROJECT_NAME=exp-a LITELLM_PORT=4001 uv run ssebench run ...
COMPOSE_PROJECT_NAME=exp-b LITELLM_PORT=4002 uv run ssebench run ...
```

Run containers then join `exp-a_agents` or `exp-b_agents` and cannot reach
each other. Each project keeps its keys and spend in its own database volume,
`<project>_postgres_data`. Results go to `results/` under the working
directory, so run each experiment from its own
[working directory](/reference/cli#working-directory) if they may run the same
task, model and agent.

## Keeping containers

`--keep-container` keeps the run container running after grading, so you can
inspect it or watch it in the [web UI](/webui/). The container stays on the
agents network, and its daemon keeps serving its API on port 4263, including
the reference patch. Stop kept containers when you are done with them:

```sh
docker ps --filter label=ssebench.webui=true
docker stop <container>
```

## Checking a deployment

- While the stack is up, this prints `true`:

  ```sh
  docker network inspect <project>_agents --format '{{.Internal}}'
  ```

- The run summary's `config.egress` tells which policy a run had.
- The [integrity bypass suite](/concepts/integrity#testing-the-protections)
  checks, among the other protections, that a container on an internal
  network cannot reach the internet.

## Next steps

- [Integrity model](/concepts/integrity)
- [LiteLLM proxy](/concepts/litellm-proxy)
- [Local stack](/deployment/compose)
