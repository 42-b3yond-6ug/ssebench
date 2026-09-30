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
agents/                claude-code, codex, opencode, dummy, reference; each has agent.yaml and a Dockerfile
models/                LiteLLM model definitions, one YAML file per provider
catalog/               task catalog service (Go)
webui/                 web UI: Vite + React client, Bun/Hono server, pty-proxy (Go)
datasets/pilot/        the pilot dataset, one folder per task, with dataset.yaml and the generated manifest.json
datasets/schema/       JSON Schemas of the task config and the manifest, exported from bench/src/ssebench/tasks/
tools/bear/            compile_commands.json generation for C tasks
tools/dataset/         third_party.py: generates datasets/pilot/THIRD_PARTY.md from third_party.json and the task configs, or checks it with --check
tools/docs/            reference.py: regenerates the generated parts of docs/reference/, or checks them with --check
tools/release/         bump.py: sets the version everywhere, or checks for drift with --check
tools/report/          Typst report from results/
tests/                 end-to-end smoke run (e2e/), integrity bypass suite (integrity/), offline test of every agent (agents/)
docs/                  VitePress documentation site
deploy/compose/        Docker Compose stack (LiteLLM proxy and Postgres); demo.yaml adds the catalog and the web UI for `just demo`
deploy/helm/           Helm chart (planned)
pyproject.toml         uv workspace root (every Python project above is a member); uv.lock pins them all
Cargo.toml, go.work    Cargo workspace (sdk/daemon) and Go workspace (catalog, runtime/entrypoint, webui/pty-proxy)
package.json           Bun workspace (webui, docs)
Justfile, just/        the recipes below
VERSION                the version of every component
flake.nix, nix/        optional Nix flake (numtide/blueprint): devshell, packages, checks, formatter
.github/workflows/     CI and release (GitHub Actions)
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
Every recipe runs without prompts, except the fzf pickers that `just run` and
`just pick` open when you give them no arguments.

| Recipe | What it does |
|---|---|
| `just setup` | Install dependencies and write `.env` with generated local secrets. |
| `just doctor` | Check Docker, disk, CPU, `.env`, the LiteLLM proxy and provider keys. |
| `just demo` / `just demo-down` | Start the demo stack (proxy, catalog, web UI), apply the known fix to a pilot task, grade it and show the run in the web UI, without an API key; `--agent <agent> --model <model>` uses your own key. `demo-down` removes what it created. |
| `just run --task <id> --agent <agent> --model <model>` | Run an agent × model × task on the pilot dataset; other options go to `ssebench run`. Without arguments it opens the fzf pickers (`just pick`). |
| `just run-all --agent <agent> --model <model>` | Run one agent × model on every pilot task, one after the other. Costs real money with a real agent. |
| `just launch` / `just stop` | Start (rebuilding when `models/` changed) or stop the LiteLLM proxy. |
| `just report [preset]` | Build the PDF report from `results/` (needs jq and Typst; reference runs are left out of the scores). |
| `just test [components]` | Unit tests: pytest, `cargo test`, `go test`, `bun test` in webui. |
| `just lint [components]` | ruff, basedpyright, cargo fmt and clippy, gofmt and go vet, webui Prettier check, typecheck and eslint. |
| `just fmt [components]` | ruff, cargo fmt, gofmt, prettier. |
| `just images` | Build the base images and the runtime, LiteLLM and catalog images (`just base-images`, `just runtime-images`); `just case-build [tasks]` and `just case-clean` build and remove case images. |
| `just dataset-verify [tasks]` | Grade tasks with the reference agent (every check must pass) and the dummy agent (the PoCs must still trigger), as the Dataset workflow does; `--changed-since origin/main` picks the tasks a branch changed. |
| `just docs [build]` | Serve or build the documentation site; the build fails on a broken link between pages. |
| `just webui` | Build and serve the web UI on `http://127.0.0.1:3001`. |
| `just docs-gen` / `just docs-check` | Regenerate, or check, the reference pages generated from the code (CLI, Python SDK, daemon API, environment variables, config files). |
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

# Reference docs: regions of docs/reference/*.md are generated from the code;
# pytest and cargo test fail when they drift. Regenerate after changing the CLI's
# options, the SDK's docstrings, sdk/daemon/openapi.yaml or docs/reference/env.yaml
uv run tools/docs/reference.py            # or --check

# Dataset: check the task folders, the committed manifest and the JSON Schemas;
# `uv run ssebench dataset manifest` (or `schema`) rewrites a stale file
uv run ssebench dataset validate
uv run ssebench dataset manifest --check
uv run ssebench dataset schema --check
# Grade tasks end to end with the reference and dummy agents (needs Docker and the base images)
uv run ssebench dataset verify <task-id> ...

# Nix (optional): every toolchain in one shell; the lint and test checks in the sandbox
nix develop
nix flake check
nix fmt

# One run end to end; the dummy agent makes no model calls, and the patch fails
uv run ssebench run --local datasets/pilot --task <task-id> --agent dummy --model <model-name>
# The reference agent applies the task's known fix, so every check passes; it needs no --model
uv run ssebench run --local datasets/pilot --task <task-id> --agent reference
```

Run results land in `results/<task>/<model>/<agent>/` under the working
directory. The CLI finds `agents/`, `images/`, `datasets/` and the Compose file
through `ssebench.paths`: `SSEBENCH_HOME` if set, otherwise the checkout that
contains the working directory, otherwise the checkout it was installed from,
otherwise the copy that the wheel carries (`uvx ssebench`, with no checkout).
`.env`, `models/` and `results/` live in the workspace: the checkout, or the
working directory without one. `uv run ssebench doctor` checks the host and
`uv run ssebench tasks list` lists the tasks, both without a model key.

Several stacks can share one Docker daemon. When you run end to end next to
other work, give yours its own Compose project (`COMPOSE_PROJECT_NAME`), proxy
port (`LITELLM_PORT`) and image prefix (`SSEBENCH_REGISTRY`), and remove only
what you created; the default project's database volume may hold someone's data.
`just demo` uses a project of its own (`SSEBENCH_DEMO_PROJECT`) for that reason.

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
- **Reference docs** are generated where they can drift: the CLI's help
  strings, the SDK's docstrings, the daemon's routes (`sdk/daemon/openapi.yaml`,
  checked by `sdk/daemon/tests/openapi.rs`) and every environment variable
  (`docs/reference/env.yaml`). When you add an option, a public SDK name, a
  daemon route or an environment variable, update its source of truth and run
  `just docs-gen`. Never edit a region between `<!-- generated: ... -->` and
  `<!-- end generated -->` by hand. `just docs-check`, `uv run pytest` and
  `cargo test --test openapi` fail on drift.
- **Other generated files** are rewritten by their tool, never edited by hand:
  `datasets/pilot/manifest.json` (`uv run ssebench dataset manifest`),
  `datasets/schema/` (`uv run ssebench dataset schema`),
  `datasets/pilot/THIRD_PARTY.md` (`python3 tools/dataset/third_party.py`),
  `uv.lock` (`uv lock`) and every version field (`just release`).
- **Docs** describe what the code does today: run a command before you document
  it. Link between pages with root-relative paths without an extension, and add a
  new page to the sidebar in `docs/.vitepress/config.mts`.
- Never commit `.env`, API keys or `results/`.

## Before you finish

Run what CI runs for the parts you touched: `just lint`, `just test` and
`just docs-check`; `bun run docs:build` when you changed `docs/`;
`uv run ssebench dataset validate`, `uv run ssebench dataset manifest --check`
and `just dataset-verify <task-id>` when you changed a task; and an end-to-end
run with the `dummy` or `reference` agent when you changed the runtime or an
image. Keep each change focused,
and report unrelated problems you find instead of fixing them in passing.

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
  | `/reference/patch.diff` | the task's reference patch, mounted read-only for the `reference` agent only |

- **The extension API is stable.** Other packages register tool layers and
  CLI commands under the `ssebench.tool_layers` and `ssebench.commands`
  entry-point groups and import from `ssebench.extensions`, and Go programs
  add container modes through `runtime/entrypoint/pkg/entrypoint`; keep all
  of them backward compatible.
- **Dataset licensing.** Task material is CC BY 4.0; upstream code in a task
  keeps its own license and license files. Only add publicly disclosed
  vulnerabilities with an upstream fix, and record them in
  `datasets/pilot/third_party.json`; `tools/dataset/third_party.py` generates
  `datasets/pilot/THIRD_PARTY.md` from it.
