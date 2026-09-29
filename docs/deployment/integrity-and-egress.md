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

### Agents without internet

The bundled agents are built for this. Each agent image installs its wrapper's
Python environment, with its interpreter, when it is built, and the wrapper
starts with `uv run --offline --no-sync`. The agents' command-line tools are
told not to reach for the internet:

| Agent | Setting | What it turns off |
|---|---|---|
| `claude-code` | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL=1` | update checks, telemetry, error reports, release notes, plugin marketplace installs |
| `codex` | `check_for_update_on_startup = false`, `analytics.enabled = false`, `otel.metrics_exporter = "none"` in `~/.codex/config.toml` | update checks, analytics, usage metrics |
| `opencode` | `OPENCODE_DISABLE_AUTOUPDATE`, `OPENCODE_DISABLE_MODELS_FETCH`, `OPENCODE_DISABLE_DEFAULT_PLUGINS`, `OPENCODE_DISABLE_LSP_DOWNLOAD` | update checks, the models.dev catalogue, default plugin installs, language server downloads |

`tests/agents` checks it: it runs every agent, in each mode it supports, on an
internal network whose only other member is a stub of the proxy that answers
every model call with "I'm done.", and requires that the agent starts, makes a
model call, finishes cleanly and is graded:

```sh
make -C images/base-images generic-go
uv run pytest tests/agents -m agents
```

An agent you add should pass it too.

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
  4263, listens on all interfaces, so one run can reach another's public view
  and its live diff. It does not serve the reference patch or any grading
  route there — only the root-only admin socket does — so a concurrent or kept
  run cannot read another run's answer through it. Use a separate Compose
  project for each experiment, as below, if even the public view should be
  private.
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
agents network, and its daemon keeps serving its API on port 4263. That port
never serves the reference patch or the grading routes, so a kept container
does not expose its answer to the other runs on the network. Stop kept
containers when you are done with them:

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
- `tests/agents` checks that each bundled agent works with no internet; see
  [Agents without internet](#agents-without-internet).

## Next steps

- [Integrity model](/concepts/integrity)
- [LiteLLM proxy](/concepts/litellm-proxy)
- [Local stack](/deployment/compose)
