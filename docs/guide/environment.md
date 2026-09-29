---
outline: deep
---

# Environment Variables

This page documents all environment variables used by SSEBench.

## Container Environment

These variables are automatically set inside task containers:

| Variable | Description | Example |
|----------|-------------|---------|
| `SSE_API_KEY` | Per-run LiteLLM key for the selected model | `sk-xxx` |
| `SSE_BASE_URL` | LiteLLM proxy URL | `http://litellm:4000` |
| `SSE_MODEL_NAME` | Selected LLM model identifier | `claude-opus-4-5` |
| `SSE_ARCHIVE` | Path for saving results/artifacts | `/tmp/sse-archive` |
| `SSE_DIFFICULTY` | Task difficulty level (0-4) | `2` |
| `TIMEOUT` | Execution timeout in seconds | `3600` |
| `SSE_KEEP_ALIVE` | `1` keeps the container running after the run (`--keep-container`) | `0` |

## Difficulty Levels

The `SSE_DIFFICULTY` variable controls which checks the agent's `test_patch` tool runs. Final grading always runs every check the task has. See [Difficulty Levels](/guide/mcp-server#difficulty-levels).

| Level | Name | `test_patch` runs |
|-------|------|-------------------|
| 0 | `FULL_ASSISTANCE` | Build + Regression + Security (PoC) + Intent |
| 1 | `NO_INTENT_TEST` | Build + Regression + Security (PoC) |
| 2 | `NO_FUTURE_TEST` | Build + Regression only (default) |
| 3 | `BUILD_ONLY` | Build only |
| 4 | `NO_BUILD` | None (debugging) |

## Host Environment

These variables should be set in the `.env` file in the repository root. The LiteLLM proxy in `deploy/compose/docker-compose.yaml` reads it.

### API Keys

```bash
# OpenAI
OPENAI_API_KEY=sk-xxx

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxx

# Google
GOOGLE_API_KEY=xxx

# Azure
AZURE_API_KEY=xxx
AZURE_API_BASE=https://your-resource.openai.azure.com/

# Hugging Face
HF_TOKEN=hf_xxx
```

The model files in `models/` reference the OpenAI, Anthropic and Google keys, so all three must be set; use a placeholder value for a provider you don't use. The Azure and Hugging Face keys are examples for models you add yourself.

## Using Environment Variables in Agents

### Python

```python
import os

# Get LLM configuration
api_key = os.environ["SSE_API_KEY"]
base_url = os.environ["SSE_BASE_URL"]
model = os.environ["SSE_MODEL_NAME"]

# Get task configuration
difficulty = int(os.environ.get("SSE_DIFFICULTY", "2"))
timeout = int(os.environ.get("TIMEOUT", "3600"))
archive_path = os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive")
```

### Shell Scripts

```bash
#!/bin/bash

# Access variables
echo "Model: $SSE_MODEL_NAME"
echo "Difficulty: $SSE_DIFFICULTY"

# Use in commands
curl -H "Authorization: Bearer $SSE_API_KEY" "$SSE_BASE_URL/models"
```

## Model Configuration

In model YAML files, reference environment variables using the `os.environ/` prefix:

```yaml
# models/openai-gpt.yaml
- model_name: gpt-4o
  litellm_params:
    model: openai/gpt-4o
    api_key: os.environ/OPENAI_API_KEY  # References OPENAI_API_KEY
```

::: warning
Never hard-code API keys in configuration files. Always use environment variable references.
:::

## .env File Example

Complete example `.env` file:

```bash
# ===================
# LLM Provider Keys
# ===================
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
GOOGLE_API_KEY=your-google-key

# ===================
# Azure Configuration
# ===================
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_API_VERSION=2024-02-01

# ===================
# Local Models
# ===================
OLLAMA_BASE_URL=http://localhost:11434
```

## Troubleshooting

### Variable Not Set

```
Error: SSE_API_KEY not set
```

- Check `.env` file exists and contains the variable
- Verify Docker Compose is reading the `.env` file
- Run `docker compose -f deploy/compose/docker-compose.yaml config` to see resolved values

### Variable Not Passed to Container

- Check variable is listed in the `deploy/compose/docker-compose.yaml` environment section
- Verify container can access host environment
- Use `docker exec <container> env` to list container variables

## Next Steps

- [Adding Models](/guide/models) - Configure model providers
- [MCP Server](/guide/mcp-server) - The `test_patch` tool
- [Getting Started](/guide/getting-started) - The `ssebench run` command
