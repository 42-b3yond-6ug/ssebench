---
outline: deep
---

# Environment variables

This page lists the environment variables SSEBench reads and sets.

## Inside the task container

`ssebench run` sets these variables in every task container. Agents and
plugins read them.

| Variable | Description | Example |
|----------|-------------|---------|
| `SSE_API_KEY` | The run's LiteLLM key, which can use only the selected model | `sk-...` |
| `SSE_BASE_URL` | URL of the LiteLLM proxy | `http://litellm:4000` |
| `SSE_MODEL_NAME` | The selected model, as named in `models/*.yaml` | `claude-sonnet-4-6` |
| `SSE_ARCHIVE` | The run's results directory, writable by the agent | `/tmp/sse-archive` |
| `SSE_DIFFICULTY` | The [difficulty level](#difficulty-levels), from 0 to 4 | `2` |
| `TIMEOUT` | How long the agent may run, in seconds | `3600` |
| `SSE_KEEP_ALIVE` | `1` keeps the container running after the run (`--keep-container`), otherwise `0` | `0` |

In sidecar mode, `SSE_DAEMON_SOCKET` also gives the path of the daemon's Unix
socket, which the two containers share.

The entrypoint also reads these optional variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SSE_DAEMON_TIMEOUT` | `300` | Seconds to wait for the daemon to start |
| `SSE_MCP_TIMEOUT` | `300` | Seconds to wait for the MCP server to start |
| `SSE_DEBUG` | unset | Any non-empty value turns on debug logging |

The MCP server writes the full logs of long check results to `MCP_LOG_DIR`
(default `/tmp/mcp/logs`); see [Long logs](/reference/mcp-server#long-logs).

## Difficulty levels

`SSE_DIFFICULTY` decides which checks the agent's `test_patch` tool runs. Final
grading always runs every check the task has.

| Level | Name |
|-------|------|
| 0 | `FULL_ASSISTANCE` |
| 1 | `NO_INTENT_TEST` |
| 2 | `NO_FUTURE_TEST` (default) |
| 3 | `BUILD_ONLY` |
| 4 | `NO_BUILD` |

See [MCP server](/reference/mcp-server#difficulty-levels) for what each level
runs.

## On the host

### Provider keys

Put the keys of your model providers in `.env` in the repository root. The
LiteLLM proxy reads this file when it starts.

```sh
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

The model files in `models/` use these three. Set the key of each provider you
use and leave out the others: the proxy still lists every model, but a model
fails when it is called without its key. A model you add can use any other
variable name, for example:

```sh
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com/
HF_TOKEN=hf_...
```

In model files, refer to a variable with the `os.environ/` prefix instead of
writing the key itself:

```yaml
- model_name: gpt-5.1
  litellm_params:
    model: openai/gpt-5.1
    api_key: os.environ/OPENAI_API_KEY
```

::: warning
Never write API keys into files that are committed. `.env` is listed in
`.gitignore`.
:::

After you change `.env` or `models/`, restart the proxy with `just launch`.

### SSEBench settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SSEBENCH_REGISTRY` | `ghcr.io/42-b3yond-6ug/ssebench` | Registry prefix for every image SSEBench builds or uses |
| `SSEBENCH_CATALOG` | unset | Catalog server that `ssebench run` gets tasks from when `--local` is not given |

## Using the variables in an agent

### Python

```python
import os

# LLM access
api_key = os.environ["SSE_API_KEY"]
base_url = os.environ["SSE_BASE_URL"]
model = os.environ["SSE_MODEL_NAME"]

# Run settings
difficulty = int(os.environ.get("SSE_DIFFICULTY", "2"))
timeout = int(os.environ.get("TIMEOUT", "3600"))
archive_path = os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive")
```

### Shell

```sh
#!/bin/bash
echo "Model: $SSE_MODEL_NAME"
echo "Difficulty: $SSE_DIFFICULTY"

# List the models this run's key can use
curl -H "Authorization: Bearer $SSE_API_KEY" "$SSE_BASE_URL/models"
```

## Troubleshooting

- **A model fails with an authentication error.** Check that its key is set in
  `.env` under the name its model file uses, then run `just launch` so the
  proxy picks it up.
- **The proxy does not start.** `.env` must exist in the repository root, even
  if it is empty. Run `docker compose -f deploy/compose/docker-compose.yaml config`
  to see the configuration Compose resolves.
- **You want to see a container's variables.** Start the run with
  `--keep-container`, then run `docker exec <container> env`.

## Next steps

- [Add a model](/guides/add-a-model): configure model providers
- [MCP server](/reference/mcp-server): the `test_patch` tool
- [CLI](/reference/cli): the options of `ssebench run`
