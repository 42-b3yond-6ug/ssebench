---
outline: deep
---

# Project structure

This page documents the SSEBench repository layout and key files.

## Overview

```
ssebench/
├── bench/               # The ssebench CLI (Python package `ssebench`)
├── runtime/
│   ├── entrypoint/      # Container entrypoint (Go)
│   ├── evaluator/       # Final grading (Python)
│   ├── mcp/             # MCP server exposing test_patch (Python)
│   └── plugins/         # Plugins that hook into the agent and grading phases
├── sdk/
│   ├── daemon/          # ssebench-daemon (Rust)
│   └── python/          # ssebench-sdk, imported as `sse` (Python)
├── images/              # Base images, LiteLLM proxy, sandbox and sidecar tool layers
├── agents/              # Agent layers: claude-code, codex, opencode, dummy, reference
├── models/              # LiteLLM model definitions, one file per provider
├── catalog/             # Task catalog service (Go)
├── webui/               # Web UI: Vite + React client, Bun/Hono server, pty-proxy (Go)
├── datasets/
│   ├── pilot/           # The pilot dataset, one folder per task
│   └── schema/          # JSON Schemas of the task config and the dataset manifest
├── tools/
│   ├── bear/            # compile_commands.json generation for C tasks
│   ├── docs/            # Generators of the reference pages, and their drift check
│   ├── release/         # Version bump and drift check (bump.py)
│   ├── report/          # Typst report built from results/
│   └── validate/        # Task validator
├── docs/                # Documentation (this site)
├── deploy/
│   └── compose/         # Docker Compose stack: LiteLLM proxy and Postgres
├── just/                # Just recipes, imported by the Justfile
├── nix/                 # Nix flake outputs: devshell, packages, checks (optional)
├── Justfile             # Task runner entry point
├── flake.nix            # Nix flake (numtide/blueprint); flake.lock pins its inputs
├── VERSION              # The version of every component
├── pyproject.toml       # uv workspace root for every Python project
├── uv.lock              # The workspace's single lockfile
├── .env.example         # Template of .env; `just setup` copies it
└── .env                 # Local secrets and API keys (not committed)
```

Run results are written to `results/`, which is not committed.

## bench/

The `ssebench` CLI. It loads the task, the agent and the model, builds the image layers for the task, runs the container and collects the results. See the [CLI reference](/reference/cli).

The code is the `ssebench` package in `bench/src/ssebench/`, with one subpackage per concern: `ssebench.cli`, `ssebench.tasks`, `ssebench.agents`, `ssebench.models`, `ssebench.pipe` (the image build pipeline), `ssebench.middleware` (the tool layers), `ssebench.runner` and `ssebench.extensions` (the [extension points](/guides/extension-points) for other packages). `ssebench.paths` locates the SSEBench home that holds `agents/`, `images/`, `datasets/` and the other assets. Tests are in `bench/tests/`.

## Python workspace

The Python projects form one [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) rooted at the repository's `pyproject.toml`: `bench`, `runtime/evaluator`, `runtime/mcp`, `runtime/plugins/*`, `sdk/python` and the agent wrappers `agents/*/*-sse`. `uv sync` at the root installs all of them into one `.venv`, and `uv.lock` pins their dependencies. The ruff, basedpyright and pytest settings live in the root `pyproject.toml`.

## runtime/

Everything that runs inside the task container besides the agent. The entrypoint starts the SDK daemon, then the [MCP server](/reference/mcp-server), then the agent as the unprivileged user `model`, and finally the evaluator, which writes `result.json`.

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
├── dummy/                 # Does nothing; for testing the pipeline
└── reference/             # Applies the task's known fix; for checking tasks
```

## models/

LLM model configurations, read by the LiteLLM proxy:

```
models/
├── anthropic-claude.yaml    # Anthropic models
├── google-gemini.yaml       # Google models
└── openai-gpt.yaml          # OpenAI models
```

See [Add a model](/guides/add-a-model) for the format.

## datasets/pilot/

One folder per task, named after the task ID, next to `dataset.yaml` (the
dataset version) and `manifest.json` (generated by `ssebench dataset manifest`).
See [Dataset manifest](/dataset/manifest) for the format of each file.

```
datasets/pilot/<task-id>/
├── Dockerfile           # Case image: the project at the vulnerable commit
└── sse/
    ├── config.yaml      # Task config
    ├── build.sh         # Build script
    ├── run.sh           # Runs a PoC
    ├── test.sh          # Runs the tests
    ├── pocs/            # Proof-of-concept inputs
    ├── reports/         # The issue or crash report given to the agent
    └── diffs/           # Reference patch and hidden tests (never shown to the agent)
```

## docs/

Documentation source (VitePress), one directory per section. See
[Writing documentation](/contributing/documentation).

```
docs/
├── .vitepress/
│   └── config.mts      # Site configuration: navigation, sidebar, search
├── getting-started/
├── concepts/
├── guides/
├── dataset/
├── reference/
├── webui/
├── deployment/
├── contributing/
└── index.md            # Homepage
```

## Next steps

- [Quickstart](/getting-started/quickstart): run your first task
- [Architecture](/concepts/architecture): how the components fit together
