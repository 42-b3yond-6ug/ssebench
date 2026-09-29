---
outline: deep
---

# Project Structure

This page documents the SSEBench repository layout and key files.

## Overview

```
ssebench/
├── bench/               # The ssebench CLI (Python)
├── runtime/
│   ├── entrypoint/      # Container entrypoint (Go)
│   ├── evaluator/       # Final grading (Python)
│   ├── mcp/             # MCP server exposing test_patch (Python)
│   └── plugins/         # Plugins that hook into the agent and grading phases
├── sdk/
│   ├── daemon/          # ssebench-daemon (Rust)
│   └── python/          # ssebench-sdk, imported as `sse` (Python)
├── images/              # Base images, LiteLLM proxy, sandbox and sidecar tool layers
├── agents/              # Agent layers: claude-code, codex, opencode, dummy
├── models/              # LiteLLM model definitions, one file per provider
├── catalog/             # Task catalog service (Go)
├── webui/               # Web UI: Vite + React client, Bun/Hono server, pty-proxy (Go)
├── datasets/
│   └── pilot/           # The pilot dataset, one folder per task
├── tools/
│   ├── bear/            # compile_commands.json generation for C tasks
│   ├── report/          # Typst report built from results/
│   └── validate/        # Task validator
├── docs/                # Documentation (this site)
├── deploy/
│   └── compose/         # Docker Compose stack: LiteLLM proxy and Postgres
├── just/                # Just recipes, imported by the Justfile
├── Justfile             # Task runner entry point
├── pyproject.toml       # Makes `uv run ssebench` work from the repository root
└── .env                 # Your API keys (not committed)
```

Run results are written to `results/`, which is not committed.

## bench/

The `ssebench` CLI. It builds the image layers for a task and runs one agent × model × task combination.

| Directory | Purpose |
|-----------|---------|
| `agents/` | Load agent configurations |
| `cli/` | Command-line interface |
| `middleware/` | Tool layers (sandbox and sidecar) |
| `models/` | LLM model lookup and per-run keys |
| `pipe/` | Docker build pipeline |
| `runner/` | Benchmark execution |
| `tasks/` | Task discovery and loading |

## runtime/

Everything that runs inside the task container besides the agent. The entrypoint starts the SDK daemon, then the [MCP server](/guide/mcp-server), then the agent as the unprivileged user `model`, and finally the evaluator, which writes `result.json`.

## images/

| Directory | Purpose |
|-----------|---------|
| `base-images/` | Toolchain images: `generic-c`, `generic-go`, `generic-rust` |
| `litellm/` | LiteLLM proxy image, configured from `models/` |
| `sandbox/` | Tool layer for sandbox mode (agent and project in one container) |
| `sidecar-agent/` | Tool layer for the agent container in sidecar mode |
| `sidecar-case/` | Tool layer for the task container in sidecar mode |
| `common/` | Scripts shared by the tool layers |

## agents/

Each agent is a folder with an `agent.yaml` and a `Dockerfile` that builds on the tool layer:

```
agents/
├── claude-code/
│   ├── claude-code-sse/   # Wrapper that runs Claude Code and writes dialog.jsonl
│   ├── agent.yaml
│   └── Dockerfile
├── codex/
├── opencode/
└── dummy/                 # Does nothing; for testing the pipeline
```

## models/

LLM model configurations, read by the LiteLLM proxy:

```
models/
├── anthropic-claude.yaml    # Anthropic models
├── google-gemini.yaml       # Google models
└── openai-gpt.yaml          # OpenAI models
```

See [Adding Models](/guide/models) for the format.

## datasets/pilot/

One folder per task, named after the task ID:

```
datasets/pilot/<task-id>/
├── Dockerfile           # Case image: the project at the vulnerable commit
└── sse/
    ├── config.yaml      # Task metadata
    ├── build.sh         # Build script
    ├── run.sh           # Runs a PoC
    ├── test.sh          # Runs the tests
    ├── pocs/            # Proof-of-concept inputs
    ├── reports/         # The issue or crash report given to the agent
    └── diffs/           # Reference patch and hidden tests (never shown to the agent)
```

## docs/

Documentation source (VitePress):

```
docs/
├── .vitepress/
│   └── config.mts      # Site configuration
├── guide/              # User guides
├── reference/          # Reference pages
└── index.md            # Homepage
```

## Next Steps

- [Getting Started](/guide/getting-started) - Setup guide
- [Architecture](/guide/architecture) - System design
