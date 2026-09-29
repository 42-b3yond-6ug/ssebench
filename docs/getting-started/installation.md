---
outline: deep
---

# Installation

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
