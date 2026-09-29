# AGENTS.md

Guidance for coding agents working in this repository. Human contributors
should read [CONTRIBUTING.md](CONTRIBUTING.md) as well.

## Project overview

SSEBench is a benchmark for AI coding agents on real security vulnerabilities
in C, Go and Rust projects. The `ssebench` CLI runs one agent × model × task
inside Docker and grades the patch the agent leaves behind.

Each run uses an image built from four layers:

1. **base**: toolchain for the language (`images/base-images/generic-{c,go,rust}`);
2. **case**: the project at the vulnerable commit plus build dependencies, from
   the task's `Dockerfile`;
3. **tool**: the SSEBench runtime (entrypoint, daemon, SDK, MCP server,
   evaluator), in a `sandbox` variant (agent and project share the container;
   the default) or a `sidecar` variant (agent in its own container;
   experimental);
4. **agent**: the agent under test, from `agents/<name>/`.

Inside the container, the Go entrypoint (`runtime/entrypoint`) starts
`ssebench-daemon` (`sdk/daemon`), then the MCP server (`runtime/mcp`), then the
agent as the unprivileged user `model`, and finally the evaluator
(`runtime/evaluator`). The evaluator writes `result.json` into the results
directory. Agents never talk to a model provider directly: every LLM call goes
through the LiteLLM proxy (`images/litellm`, models in `models/*.yaml`).

The difficulty level (`SSE_DIFFICULTY`) controls which checks the agent's
`test_patch` tool runs. Final grading always runs every check the task has.

| Level | Name | `test_patch` runs |
|---|---|---|
| 0 | `FULL_ASSISTANCE` | build, functional tests, PoC, intent tests |
| 1 | `NO_INTENT_TEST` | build, functional tests, PoC |
| 2 | `NO_FUTURE_TEST` (default) | build, functional tests |
| 3 | `BUILD_ONLY` | build |
| 4 | `NO_BUILD` | nothing |

## Where things live

```
bench/                 ssebench CLI (Python package in bench/src/ssebench): agents, models, tasks, image pipeline, runner
runtime/entrypoint/    container entrypoint (Go)
runtime/evaluator/     final grading (Python)
runtime/mcp/           MCP server exposing test_patch (Python)
runtime/plugins/       plugins and plugins.yaml (hooks around agent and grading)
sdk/daemon/            ssebench-daemon (Rust, actix-web)
sdk/python/            ssebench-sdk, import name `sse` (Python)
images/                base images, litellm, sandbox and sidecar tool layers, shared scripts
agents/                claude-code, codex, opencode, dummy; each has agent.yaml and a Dockerfile
models/                LiteLLM model definitions, one YAML file per provider
catalog/               task catalog service (Go)
webui/                 web UI: Vite + React client, Bun/Hono server, pty-proxy (Go)
datasets/pilot/        the pilot dataset, one folder per task
tools/bear/            compile_commands.json generation for C tasks
tools/report/          Typst report from results/
tools/validate/        task validator
docs/                  VitePress documentation site
deploy/compose/        Docker Compose stack (LiteLLM proxy and Postgres)
deploy/helm/           Helm chart (planned)
pyproject.toml         uv workspace root (every Python project above is a member); uv.lock pins them all
.github/workflows/     CI (GitHub Actions)
```

A task folder in `datasets/pilot/<task-id>/` contains a `Dockerfile` for the
case image and `sse/` with `config.yaml`, `build.sh`, `run.sh`, `test.sh`,
`pocs/`, `reports/` (what the agent is told) and `diffs/` (the reference patch
and hidden tests; never exposed to the agent).

## Commands

The root `Justfile` is the front door. Recipes marked *planned* are not in the
Justfile yet; `just --list` shows what exists. Until then, use the
per-component commands below.

| Recipe | What it does |
|---|---|
| `just setup` | Install dependencies and write `.env` with generated local secrets. *planned* |
| `just demo` | Apply the known fix to a pilot task, grade it and show the run in the web UI, without an API key. *planned* |
| `just run` | Run an agent × model × task; interactive pickers when arguments are omitted. *planned* |
| `just test` | Unit tests for every component. *planned* |
| `just lint` | ruff, basedpyright, clippy, go vet, eslint. *planned* |
| `just fmt` | ruff format, cargo fmt, gofmt, prettier. *planned* |
| `just images` | Build the base, tool and agent images. *planned* |
| `just dataset-validate` | Check that tasks build, their PoCs reproduce and their tests behave. *planned* |
| `just docs` | Serve or build the documentation site. *planned* |
| `just release <version>` | Bump the single project version across every component. *planned* |

Per component:

```sh
# Python: one uv workspace (bench, runtime/evaluator, runtime/mcp, runtime/plugins/*,
# sdk/python, agents/*/*-sse); run from the repository root
uv sync
uv run ruff format && uv run ruff check
uv run basedpyright
uv run pytest

# Rust (sdk/daemon)
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test

# Go (runtime/entrypoint, catalog, webui/pty-proxy)
gofmt -l . && go vet ./... && go test ./...

# Web UI (webui) and docs (docs)
bun install
bun run lint && bun run typecheck && bun run build    # webui
bun run build                                          # docs

# One run end to end; the dummy agent makes no model calls
uv run ssebench run --local datasets/pilot --task <task-id> --agent dummy --model <model-name>
```

Run results land in `results/<task>/<model>/<agent>/` under the working
directory. The CLI finds `agents/`, `images/`, `datasets/` and the Compose file
through `ssebench.paths`: `SSEBENCH_HOME` if set, otherwise the checkout that
contains the working directory, otherwise the checkout it was installed from.

## Conventions

- **Python:** 3.12 or newer, managed with uv. Format and lint with ruff; type
  check with basedpyright (pyright). Use modern typing (`X | None`,
  `list[str]`) and dataclasses or pydantic models for structured data.
- **Rust:** stable toolchain; `cargo fmt` and `cargo clippy -D warnings` must
  be clean. Use `anyhow` for error handling in the daemon.
- **Go:** `gofmt` and `go vet` clean.
- **TypeScript:** Bun for installs and scripts; eslint, prettier and `tsc`
  clean.
- **Commits:** `type(scope): description` (`feat`, `fix`, `docs`, `refactor`,
  `test`, `build`, `ci`, `chore`, `style`), with the component as the scope.
  Disclose AI assistance with an `Assisted-by:` trailer naming the tool and
  model.
- **Comments** explain the non-obvious reason, not what the code does.
- **Versions** move in lockstep: every component shares one version number.
  Datasets are versioned separately (for example `pilot-v1`).
- Never commit `.env`, API keys or `results/`.

## Invariants to preserve

- **Benchmark integrity.** Nothing the agent can reach while it works may
  reveal the reference patch, the hidden tests, the upstream fix commit, or a
  check that its difficulty level withholds. The agent runs as `model` (uid
  1000); task metadata and reference files are root-only; the project's git
  history is replaced by a single commit. Treat any change that weakens this
  as a security bug, and add a test that tries the bypass.
- **Plugins never change the grade.** A plugin that fails or times out must
  not alter the evaluation result.
- **The container contract is stable.** Agents, plugins and third-party
  extensions rely on it. Change it only together with the runtime, the SDK,
  the agents and the docs:

  | Item | Value |
  |---|---|
  | `SSE_BASE_URL`, `SSE_API_KEY`, `SSE_MODEL_NAME` | LiteLLM proxy endpoint, key and model name for the agent |
  | `SSE_DIFFICULTY` | difficulty level, 0 to 4 |
  | `SSE_ARCHIVE` | results directory inside the container |
  | `TIMEOUT` | agent time limit in seconds |
  | `SSE_DAEMON_SOCKET` | daemon Unix socket (default `/tmp/sse.sock`) |
  | `SSE_KEEP_ALIVE`, `SSE_DEBUG` | keep the container after the run; verbose entrypoint logs |
  | daemon HTTP port | 4263 |
  | MCP server | port 3000, path `/mcp` |
  | OpenCode server | port 4096, when the agent image includes OpenCode |
  | `dialog.jsonl` | the agent dialog in the results directory, read by the web UI |

- **Dataset licensing.** Task material is CC BY 4.0; upstream code in a task
  keeps its own license and license files. Only add publicly disclosed
  vulnerabilities with an upstream fix, and record them in
  `datasets/pilot/THIRD_PARTY.md`.
