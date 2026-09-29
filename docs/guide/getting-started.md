---
outline: deep
---

# Getting Started

This guide sets up SSEBench on your machine and runs one agent on one task from the `pilot` dataset.

## Prerequisites

SSEBench requires the following tools:

| Tool | Description |
|------|-------------|
| `docker` | Container runtime for isolated environments, with buildx |
| `uv` | Fast Python package manager; runs the `ssebench` CLI |
| `just` | Task runner for build commands |
| `fzf` | Fuzzy finder for interactive selection (optional) |
| `jq` | JSON processor (optional, for reports) |
| `bun` | JavaScript runtime for the Web UI (optional) |

An x86-64 host is recommended: many C tasks build with AddressSanitizer for amd64 only.

### Installation

::: code-group

```sh [Ubuntu/Debian]
# Install system dependencies
apt-get install -y docker.io jq fzf

# Install just
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```sh [macOS]
# Install with Homebrew
brew install docker jq fzf just

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```sh [Arch Linux]
# Install system dependencies
pacman -S docker jq fzf just

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

:::

## Get the Code

```bash
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
```

## Environment Setup

Before running any benchmarks, create a `.env` file in the repository root with your API keys:

```bash
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx
```

::: info
All three keys must be present. If you don't use a provider, use a placeholder value (e.g., `GOOGLE_API_KEY=fake-key`).
:::

::: warning
Never commit your `.env` file. It's already in `.gitignore`.
:::

## Quick Start

1. **Build the base images**

   ```bash
   just base-images
   ```

   This builds the C, Go and Rust toolchain images that every pilot task starts from.

2. **Start the LiteLLM proxy**

   ```bash
   just launch
   ```

   This builds and starts the Docker Compose stack in `deploy/compose/docker-compose.yaml`: the LiteLLM proxy on port 4000 and its Postgres database.

3. **Run a task**

   ```bash
   uv run ssebench run \
       --local datasets/pilot \
       --task generic-c-jq-jq_gh_3196 \
       --agent claude-code \
       --model claude-sonnet-4-5
   ```

   The first run of a task builds its case, tool and agent images, which can take a while.

::: tip
Use `--agent dummy` to check the pipeline end to end. The dummy agent exits immediately and makes no model calls, so the evaluator grades the unmodified source tree.
:::

## The `ssebench run` Command

| Argument | Default | Description |
|----------|---------|-------------|
| `--model` | *(required)* | Model name, as defined in `models/*.yaml` |
| `--agent` | *(required)* | Agent name, a directory under `agents/` |
| `--task` | *(required)* | Task ID, the name of the task's folder |
| `--local PATH` | | Dataset directory that contains the task folder, e.g. `datasets/pilot` |
| `--mode` | `sandbox` | Execution mode: `sandbox` or `sidecar` |
| `--timeout` | `3600` | Agent timeout in seconds |
| `--difficulty` | `2` | Which checks the agent's `test_patch` tool may run (0-4); see [Difficulty Levels](/guide/mcp-server#difficulty-levels) |
| `--keep-container` | off | Keep the container after the run, for example to inspect it from the Web UI |

`uv run ssebench build-case --benchmarks <dataset-dir> [--tasks a,b] [--force]` builds only the case images of a dataset.

## Results

Each run writes to `results/<task>/<model>/<agent>/`:

- `result.json`: the evaluator's grade;
- `dialog.jsonl`: the agent's session, in the [dialog protocol](/guide/dialog-protocol) format;
- a snapshot of the final source tree, and the logs of every component.

A summary of the run is also written to `results/<task>-<agent>-<model>.json`.

## Verifying Your Setup

```bash
# Check Docker
docker --version

# Check just
just --version

# List available commands
just

# Verify the LiteLLM proxy is running
curl http://localhost:4000/health/liveliness
```

## Web UI

SSEBench includes a Web UI for launching runs and watching them live.

### Starting the Web UI

The Web UI requires [Bun](https://bun.sh/). From the repository root:

```bash
cd webui
bun install
bun run prod
```

This builds the frontend and starts the production server. Once started, open your browser to `http://localhost:3001`.

::: info Remote Server Access
If you're running SSEBench on a remote server, you have two options:

1. **Direct access**: Navigate to `http://<your-server-ip>:3001`. Make sure port 3001 is open in your server's firewall.

2. **SSH tunnel (recommended)**: Forward the port through SSH for secure access without opening firewall ports:
   ```bash
   ssh -L 3001:localhost:3001 user@your-server
   ```
   Then access the Web UI at `http://localhost:3001` from your local machine.
:::

### Features

The Web UI provides:
- **Task Browser**: Browse and select benchmark tasks
- **Launch Wizard**: Configure and launch benchmarks interactively
- **Live Logs**: Stream launch output in real-time
- **Container Management**: Attach to running containers, view terminal output
- **AI Session Viewer**: Monitor agent conversations and tool executions

::: tip
Make sure the LiteLLM proxy is running (`just launch`) before launching tasks from the Web UI.
:::

## Next Steps

- [Architecture](/guide/architecture) - Understand the system design
- [Adding Models](/guide/models) - Integrate new LLM models
- [MCP Server](/guide/mcp-server) - The `test_patch` tool and difficulty levels
- [Project Structure](/reference/project-structure) - Repository layout
