---
outline: deep
---

# LiteLLM proxy

Agents never call a model provider directly. Every model request from a run
goes through a local [LiteLLM](https://docs.litellm.ai/) proxy, which
translates it for the provider of the chosen model. This is what lets any
agent run with any model: the agent speaks the API it was written for, and the
model is only a name.

```
                                 +-- Compose project (default: ssebench) ---------------+
run container                    |                                                      |
  agent                          |   litellm  :4000  ------------------->  providers    |
    SSE_BASE_URL=http://litellm:4000     |  master key, provider keys     (Anthropic,   |
    SSE_API_KEY=<run key>  ----------->  |  model list from models/        OpenAI,      |
    SSE_MODEL_NAME=<model>       |       v                                 Google, ...) |
                                 |   litellm_db (Postgres)  keys, budgets, spend        |
                                 +------------------------------------------------------+
ssebench CLI (host) --- http://localhost:$LITELLM_PORT, master key: create key, read spend
```

## The stack

The proxy runs as a Docker Compose stack, `deploy/compose/docker-compose.yaml`,
with two services:

| Service | Image | Role |
|---|---|---|
| `litellm` | `$SSEBENCH_REGISTRY/litellm:<version>`, built from `images/litellm/` | The proxy. It publishes port 4000 on the host as `LITELLM_PORT` (default 4000). |
| `litellm_db` | `postgres:16` | LiteLLM's database: the per-run keys, their budgets and their spend. Its data is in the `postgres_data` volume, which `down` keeps. |

The proxy reads `LITELLM_MASTER_KEY` and the Postgres password from the
environment, and the provider keys from `.env` in the repository root.
`just setup` generates the two secrets; you add the provider keys. See
[Environment variables](/reference/environment#on-the-host).

The Compose project is `COMPOSE_PROJECT_NAME` (default `ssebench`). Its
containers, networks and volume carry that name, so stacks with different
names and ports run side by side on one host. The proxy is on two networks of
the project: `<project>_default`, a normal bridge through which it reaches the
providers, and `<project>_agents`, an internal network that run containers
join by default. See [Integrity and egress](/deployment/integrity-and-egress).

## Starting and stopping

| Command | Does |
|---|---|
| `ssebench proxy up`, `just launch` | Build the proxy image if it is missing or out of date, start the stack, and wait up to three minutes for `/health/liveliness` to answer. |
| `ssebench proxy build` | Only build the image, if it is missing or out of date. |
| `ssebench proxy down`, `just stop` | Stop the stack and remove its containers and networks. The database volume is kept. |
| `--rebuild` | With `up` or `build`: rebuild the image even if it is current. |

You rarely need these: `ssebench run` runs the equivalent of `proxy up` before
every run. `ssebench doctor` checks whether the proxy answers.

## The model list

The models the proxy offers are defined in `models/*.yaml`, one file per
provider. Each entry gives the name that `--model` uses and LiteLLM's
parameters for it:

```yaml
- model_name: claude-sonnet-4-6
  litellm_params:
    model: anthropic/claude-sonnet-4-6
    api_key: os.environ/ANTHROPIC_API_KEY
  model_info:
    input_cost_per_token: 3.0e-06
    output_cost_per_token: 1.5e-05
```

The list is **baked into the proxy image**. When the image is built,
`images/litellm/config_gen.py` merges every `.yaml` and `.yml` file in `models/`
into LiteLLM's configuration, `/litellm-config.yaml`, together with the master
key and a few global settings (a 600-second request timeout, and dropping or
adapting request parameters a provider does not support). So a change to
`models/` takes effect only once the image is rebuilt.

The CLI does that for you. It hashes `models/*.yaml`, `models/*.yml` and the
files in `images/litellm/`, and stores the hash in the image's
`ssebench.litellm-config` label. `proxy up`, `proxy build` and `ssebench run`
compare the label with the current files and rebuild the image when they
differ, and Compose then recreates the proxy container. Provider keys are not
part of the image: after changing them in `.env`, run `just launch` so the
proxy restarts with them.

The `model_info` costs are what the proxy charges each run's key, so keep them
in line with the provider's prices. To add a model, see
[Add a model](/guides/add-a-model).

## One key per run

Before each run, `ssebench run` uses the master key to:

1. check that the proxy has the model: `GET /models/<name>` must succeed,
   otherwise the run stops with `Model <name> does not exist.`;
2. create a new LiteLLM user that may use **only that model**, with a budget of
   10 US dollars, and take the key LiteLLM returns for it (`POST /user/new`).

The key goes into the run container; the master key never does. After the run,
the CLI reads the user's spend (`GET /user/info`) and records it as `spend` in
the [run summary](/concepts/results#the-summary). Since every run has its own
user, that is exactly what the run cost.

## What the agent gets

The run container gets three variables:

| Variable | Value |
|---|---|
| `SSE_BASE_URL` | `http://litellm:4000`, the proxy by its service name on the Compose network |
| `SSE_API_KEY` | The run's key |
| `SSE_MODEL_NAME` | The model name, as in `models/*.yaml` |

LiteLLM serves both an OpenAI-compatible API (`/v1/chat/completions`,
`/v1/responses`) and an Anthropic-compatible one (`/v1/messages`), so each
agent keeps its own client and is only pointed at the proxy:

| Agent | Configuration |
|---|---|
| `claude-code` | `ANTHROPIC_BASE_URL=$SSE_BASE_URL`, `ANTHROPIC_AUTH_TOKEN=$SSE_API_KEY`, and the model name for every model slot |
| `codex` | A model provider with base URL `$SSE_BASE_URL` and the Responses API, keyed by `SSE_API_KEY` |
| `opencode` | An OpenAI-compatible provider at `$SSE_BASE_URL/v1` |
| `dummy` | Makes no model calls |

An agent of your own does the same; see [Add an agent](/guides/add-an-agent)
and the [container contract](/guides/extension-points#environment-variables).

## Next steps

- [Add a model](/guides/add-a-model): define another model or provider
- [Integrity and egress](/deployment/integrity-and-egress): what else a run
  container can reach
- [CLI](/reference/cli#ssebench-proxy): `ssebench proxy`
