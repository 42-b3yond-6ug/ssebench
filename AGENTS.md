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
runtime/entrypoint/    container entrypoint (Go): library in pkg/entrypoint, binary in cmd/ssebench-entrypoint
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
datasets/pilot/        the pilot dataset, one folder per task, with dataset.yaml and the generated manifest.json
datasets/schema/       JSON Schemas of the task config and the manifest, exported from bench/src/ssebench/tasks/
tools/bear/            compile_commands.json generation for C tasks
tools/release/         bump.py: sets the version everywhere, or checks for drift with --check
tools/report/          Typst report from results/
tools/validate/        task validator
docs/                  VitePress documentation site
deploy/compose/        Docker Compose stack (LiteLLM proxy and Postgres)
deploy/helm/           Helm chart (planned)
pyproject.toml         uv workspace root (every Python project above is a member); uv.lock pins them all
flake.nix, nix/        optional Nix flake (numtide/blueprint): devshell, packages, checks, formatter
.github/workflows/     CI (GitHub Actions)
```

A task folder in `datasets/pilot/<task-id>/` contains a `Dockerfile` for the
case image and `sse/` with `config.yaml`, `build.sh`, `run.sh`, `test.sh`,
`pocs/`, `reports/` (what the agent is told) and `diffs/` (the reference patch
and hidden tests; never exposed to the agent). The folder name is the task ID,
and `sse/config.yaml` follows `TaskMetadata` in `bench/src/ssebench/tasks/metadata.py`
(docs/dataset/manifest.md describes every key). After changing a task,
regenerate the manifest, which records a checksum of every task file.

## Commands

The root `Justfile` is the front door; `just` lists its recipes by group.
Every recipe runs without prompts. Recipes marked *planned* are not in the
Justfile yet.

| Recipe | What it does |
|---|---|
| `just setup` | Install dependencies and write `.env` with generated local secrets. |
| `just doctor` | Check Docker, disk, CPU, `.env`, the LiteLLM proxy and provider keys. |
| `just demo` | Apply the known fix to a pilot task, grade it and show the run in the web UI, without an API key. *planned* |
| `just run --task <id> --agent <agent> --model <model>` | Run an agent × model × task on the pilot dataset; other options go to `ssebench run`. Without arguments it opens the fzf pickers (`just pick`). |
| `just launch` / `just stop` | Start (rebuilding when `models/` changed) or stop the LiteLLM proxy. |
| `just test [components]` | Unit tests: pytest, `cargo test`, `go test`, `bun test` in webui. |
| `just lint [components]` | ruff, basedpyright, cargo fmt and clippy, gofmt and go vet, webui typecheck and eslint (eslint findings are reported, not enforced yet). |
| `just fmt [components]` | ruff, cargo fmt, gofmt, prettier. |
| `just images` | Build the base images and the runtime, LiteLLM and catalog images. |
| `just dataset-validate [tasks]` | Check that tasks build, their PoCs reproduce and their tests behave. |
| `just docs [build]` | Serve or build the documentation site. |
| `just release <version>` | Set the version of every component and update the lockfiles. |

Components are `python`, `rust`, `go` and `webui`; without arguments a recipe
covers all of them.

Per component:

```sh
# Python: one uv workspace (bench, runtime/evaluator, runtime/mcp, runtime/plugins/*,
# sdk/python, agents/*/*-sse); run from the repository root
uv sync
uv run ruff format && uv run ruff check
uv run basedpyright
uv run pytest

# Rust: Cargo workspace at the root (sdk/daemon), toolchain in rust-toolchain.toml
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test

# Go: go.work at the root (runtime/entrypoint, catalog, webui/pty-proxy)
gofmt -l runtime/entrypoint catalog webui/pty-proxy
go vet work && go test work

# Web UI and docs: Bun workspace at the root (webui, docs)
bun install
bun run build                                          # webui and docs
bun run --cwd webui lint && bun run --cwd webui typecheck

# Dataset: check the task folders, the committed manifest and the JSON Schemas;
# `uv run ssebench dataset manifest` (or `schema`) rewrites a stale file
uv run ssebench dataset validate
uv run ssebench dataset manifest --check
uv run ssebench dataset schema --check

# Nix (optional): every toolchain in one shell; the lint and test checks in the sandbox
nix develop
nix flake check
nix fmt

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
- **Rust:** the stable toolchain pinned in `rust-toolchain.toml`; `cargo fmt`
  and `cargo clippy -D warnings` must be clean. Use `anyhow` for error handling in the daemon.
- **Go:** `gofmt` and `go vet` clean.
- **TypeScript:** Bun for installs and scripts; eslint, prettier and `tsc`
  clean.
- **Commits:** `type(scope): description` (`feat`, `fix`, `docs`, `refactor`,
  `test`, `build`, `ci`, `chore`, `style`), with the component as the scope.
  Disclose AI assistance with an `Assisted-by:` trailer naming the tool and
  model.
- **Comments** explain the non-obvious reason, not what the code does.
- **Versions** move in lockstep: every component shares the version in
  `VERSION` (SemVer; Python projects carry its PEP 440 form). Never edit a
  version field by hand: use `just release <version>`, and
  `uv run tools/release/bump.py --check` to find drift. Datasets are
  versioned separately (for example `pilot-v1`); see
  `docs/contributing/releasing.md`.
- Never commit `.env`, API keys or `results/`.

## Invariants to preserve

- **Benchmark integrity.** Nothing the agent can reach while it works may
  reveal the reference patch, the hidden tests, the upstream fix commit, or a
  check that its difficulty level withholds. The agent runs as `model` (uid
  1000); task metadata and reference files are root-only; the project's git
  history is replaced by a single commit. The daemon enforces this, not just
  the MCP server: it reads `SSE_DIFFICULTY` at startup and rejects withheld
  `bencher` actions (403) on the agent-facing listeners, and it serves the
  reference patch (`GET /reference/patch`) only on the privileged admin socket
  or, on the agent-facing listeners, after the agent phase has ended (the
  entrypoint signals `POST /admin/agent_exited` over the admin socket, which is
  how the web UI reads the patch from the host post-run). Grading goes through
  the admin socket so it runs every check regardless of difficulty. By default
  a run container has no internet, only the LiteLLM proxy (`--egress open`
  opts out). Treat any change that weakens this as a security bug, and add a
  test to `tests/integrity/` that tries the bypass.
- **Plugins never change the grade.** A plugin that fails or times out must
  not alter the evaluation result.
- **The container contract is stable.** Agents, plugins and third-party
  extensions rely on it. Change it only together with the runtime, the SDK,
  the agents and the docs (`docs/guides/extension-points.md` has the full
  list):

  | Item | Value |
  |---|---|
  | `SSE_BASE_URL`, `SSE_API_KEY`, `SSE_MODEL_NAME` | LiteLLM proxy endpoint, key and model name for the agent |
  | `SSE_DIFFICULTY` | difficulty level, 0 to 4 |
  | `SSE_ARCHIVE` | results directory inside the container |
  | `TIMEOUT` | agent time limit in seconds |
  | `SSE_DAEMON_SOCKET` | agent-facing daemon Unix socket, 0666 (default `/tmp/sse.sock`) |
  | `SSE_ADMIN_SOCKET` | privileged daemon Unix socket, 0600 root-only (default `/run/ssebench/admin.sock`) |
  | `SSE_KEEP_ALIVE`, `SSE_DEBUG` | keep the container after the run; verbose entrypoint logs |
  | daemon HTTP port | 4263 (agent-facing) |
  | MCP server | port 3000, path `/mcp` |
  | OpenCode server | port 4096, when the agent image includes OpenCode |
  | `dialog.jsonl` | the agent dialog in the results directory, read by the web UI |

- **The extension API is stable.** Other packages register tool layers and
  CLI commands under the `ssebench.tool_layers` and `ssebench.commands`
  entry-point groups and import from `ssebench.extensions`, and Go programs
  add container modes through `runtime/entrypoint/pkg/entrypoint`; keep all
  of them backward compatible.
- **Dataset licensing.** Task material is CC BY 4.0; upstream code in a task
  keeps its own license and license files. Only add publicly disclosed
  vulnerabilities with an upstream fix, and record them in
  `datasets/pilot/THIRD_PARTY.md`.
