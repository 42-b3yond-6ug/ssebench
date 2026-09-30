# Contributing to SSEBench

Thanks for helping. Bug reports, fixes, new tasks, new agents and documentation
improvements are all welcome.

- Questions, bugs and feature requests go in GitHub issues.
- Security problems, including ways for an agent to reach the reference answer,
  must be reported privately; see [SECURITY.md](SECURITY.md).
- Everyone taking part is expected to follow the
  [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

You need:

- Docker with buildx;
- [just](https://just.systems/);
- Python 3.12 or newer and [uv](https://docs.astral.sh/uv/);
- if you work on the daemon, the Go services or the web UI and docs: Rust at
  the release `rust-toolchain.toml` pins (rustup selects it by itself), Go
  1.26 or newer, [Bun](https://bun.sh/) at the version `packageManager` in
  `package.json` pins, and a C compiler for linking Rust.

[Nix](https://nixos.org/) is optional; see [With Nix](#with-nix).

```sh
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
just setup
```

`just setup` installs the dependencies and writes `.env` with generated local
secrets for the LiteLLM proxy and its database. Add your provider keys to
`.env` to run real agents. `.env` is ignored by git; never commit it.
`just doctor` checks Docker, disk space and `.env`, and says how to fix what is
wrong; see [Installation](docs/getting-started/installation.md) and
[Troubleshooting](docs/getting-started/troubleshooting.md).

Each toolchain works from the repository root on its own, too:

```sh
uv sync          # Python: every workspace member into .venv
cargo build      # Rust: the Cargo workspace (ssebench-daemon)
go build work    # Go: every module in go.work
bun install      # TypeScript: the Bun workspace (webui, docs)
```

### With Nix

The flake gives you the same toolchains without installing them one by one:

- `nix develop` opens a shell with Python 3.12, uv, Rust (the pinned release,
  with clippy, rustfmt and rust-analyzer), Go, Bun, just, Typst, the Docker CLI
  with buildx and compose, fzf, jq, actionlint, gitleaks and a C compiler. uv
  uses the shell's Python and never downloads one. The Docker engine still
  comes from your system. On NixOS, the prebuilt binaries uv installs (ruff,
  and the Node.js that basedpyright runs on) need
  [nix-ld](https://github.com/nix-community/nix-ld).
- `nix flake check` runs the formatting check, ruff, basedpyright, pytest,
  clippy, `go vet`, the Rust, Go and web UI unit tests, and every package
  build, all in the Nix sandbox.
- `nix fmt` formats Python, Rust, Go and Nix files. The web UI has its own
  Prettier setup: `bun run --cwd webui format`.
- `nix build .#<name>` builds `ssebench` (the CLI, also the default),
  `ssebench-sdk`, `ssebench-wheels`, `ssebench-daemon` (statically linked;
  Linux only), `ssebench-entrypoint`, `ssebench-catalog`, `pty-proxy`, `webui`
  and `docs`.

The flake covers x86-64 and ARM64 Linux and Apple silicon macOS.

## Checks and tests

```sh
just fmt         # format all code
just lint        # all linters and type checkers
just test        # unit tests for every component
just docs-check  # generated reference pages, JSON Schemas and the daemon's OpenAPI description
```

`fmt`, `lint` and `test` take component names to narrow them down (`python`,
`rust`, `go`, `webui`), for example `just test python` or `just lint rust go`.
Run `just lint`, `just test` and `just docs-check` before you open a pull
request; CI runs the same checks, on the parts of the tree your change touches.
Markdown is not linted, but `bun run docs:build` builds the documentation site
and fails on a broken link between pages, so run it when you change `docs/`.

While iterating on one component, you can run its tools directly:

| Component | Paths | Commands |
|---|---|---|
| Python | `bench/`, `runtime/evaluator/`, `runtime/mcp/`, `runtime/plugins/`, `sdk/python/`, `agents/*/*-sse/` | `uv run ruff format`, `uv run ruff check`, `uv run basedpyright`, `uv run pytest` (one uv workspace; run from the repository root) |
| Rust | `sdk/daemon/` | `cargo fmt`, `cargo clippy --all-targets -- -D warnings`, `cargo test` |
| Go | `runtime/entrypoint/`, `catalog/`, `webui/pty-proxy/` | `gofmt -l .`, `go vet ./...`, `go test ./...` |
| TypeScript | `webui/` | `bun run lint`, `bun run typecheck`, `bun run build` |
| Docs | `docs/` | `bun run build`; `just docs-check` checks the generated reference pages and `just docs-gen` rewrites them |
| Dataset | `datasets/`, `tools/dataset/` | `uv run ssebench dataset validate`, `uv run ssebench dataset manifest --check`, `python3 tools/dataset/third_party.py --check` |

### Generated reference docs

Parts of the reference pages under `docs/reference/` are generated from the code
so that they cannot drift from it. Do not edit the regions between
`<!-- generated: ... -->` and `<!-- end generated -->`. Change the source of
truth, then run `just docs-gen`:

| You change | Edit | Then |
|---|---|---|
| A CLI command or option | the help strings of the argument parser in `bench/src/ssebench/cli/` | `just docs-gen` |
| A public name of the `sse` SDK | its docstring in `sdk/python/sse/` | `just docs-gen` |
| A daemon route or a response field | `sdk/daemon/openapi.yaml` | `just docs-gen` |
| An environment variable | `docs/reference/env.yaml` | `just docs-gen` |

`just docs-check`, `uv run pytest` (`tools/docs/test_refdocs.py`) and
`cargo test --test openapi` fail when a page or the OpenAPI description is out
of date, so commit the regenerated files with your change.
[Writing documentation](docs/contributing/documentation.md) has the details.

### End to end

Changes to the runtime, the images or a task should also be tried end to end.
The `dummy` agent makes no model calls, so a run with it exercises image
builds, the entrypoint and grading without spending tokens:

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent dummy --model <model-name>
```

The `reference` agent applies the task's known fix instead, so a sound task
passes every check; use it to check a task you add or change:

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent reference
```

## Component map

| Path | Language | What it is |
|---|---|---|
| `bench/` | Python | The `ssebench` CLI: image layers, runs, results. |
| `runtime/entrypoint/` | Go | Container entrypoint: starts the daemon, MCP server, agent and evaluator. |
| `runtime/evaluator/` | Python | Grades the final source tree. |
| `runtime/mcp/` | Python | MCP server with the `test_patch` tool. |
| `runtime/plugins/` | Python, shell | Plugins hooked before, during or after the agent and grading phases. |
| `sdk/daemon/` | Rust | `ssebench-daemon`: build, PoC and test actions over a Unix socket and HTTP. |
| `sdk/python/` | Python | `ssebench-sdk` (`import sse`): client used inside task containers. |
| `images/` | Dockerfiles | Base images, the LiteLLM proxy image, sandbox and sidecar tool layers. |
| `agents/` | Dockerfiles, Python | One folder per agent. |
| `models/` | YAML | LiteLLM model definitions. |
| `catalog/` | Go | Task catalog service. |
| `webui/` | TypeScript, Go | Web UI and its terminal proxy. |
| `datasets/pilot/` | mixed | The pilot tasks, `dataset.yaml`, the generated `manifest.json`, `third_party.json` and the `THIRD_PARTY.md` generated from it. |
| `datasets/schema/` | JSON | JSON Schemas of the task config, `dataset.yaml` and the manifest, generated from the CLI's models. |
| `tools/` | shell, Python, Typst | Task preprocessing (`bear`), the third-party license file (`dataset`), reference docs generation (`docs`), version bumps (`release`), reports (`report`). |
| `tests/` | Python, shell | End-to-end smoke run, integrity bypass suite, offline test of every agent. |
| `docs/` | Markdown | Documentation site (VitePress). |
| `deploy/` | YAML | Deployment configurations (Docker Compose). |
| `nix/`, `flake.nix` | Nix | The optional flake: development shell, packages, checks, formatter. |
| `just/`, `Justfile` | just | The recipes. |

## Extending SSEBench

- **Add a task:** [docs/guides/add-a-task.md](docs/guides/add-a-task.md). Tasks
  must be publicly disclosed vulnerabilities with an upstream fix. A new task
  must pass `uv run ssebench dataset validate` and `just dataset-verify
  <task-id>`, which the Dataset workflow runs on every pull request that
  changes a task: every check must pass with the `reference` agent, while the
  `dummy` agent must fail its proof-of-concept and hidden-test checks.
  Regenerate `datasets/pilot/manifest.json` with `uv run ssebench dataset
  manifest`. Record the upstream project and license in
  `datasets/pilot/third_party.json`, then regenerate
  `datasets/pilot/THIRD_PARTY.md` with `python3 tools/dataset/third_party.py`.
- **Add an agent:** [docs/guides/add-an-agent.md](docs/guides/add-an-agent.md).
  An agent is a folder in `agents/` with an `agent.yaml` and a Dockerfile; an
  agent with a Python wrapper (`agents/<name>/<name>-sse`) is a member of the
  uv workspace, so run `uv lock` and keep its version equal to `VERSION`
  (`uv run tools/release/bump.py --check`). An agent must not need the
  network when it runs, since runs restrict it by default.
- **Add a model:** [docs/guides/add-a-model.md](docs/guides/add-a-model.md).
  Add the model to a file in `models/` and its key to `.env`; `just launch`
  rebuilds the proxy.
- **Write a plugin or extend the runtime:**
  [docs/guides/write-a-plugin.md](docs/guides/write-a-plugin.md).

## Dataset changes

The pilot dataset is a benchmark, so its files are held to a few rules:

- **Only publicly disclosed vulnerabilities with an upstream fix.** Never add a
  vulnerability that is not public yet, or one whose fix you cannot point to. A
  task must not contain anything that reveals its reference patch or hidden tests
  to the agent; see [SECURITY.md](SECURITY.md).
- **Record where everything comes from.** Add the upstream project, its license,
  the advisory, the report and the origin of the PoC to
  `datasets/pilot/third_party.json`, then regenerate
  `datasets/pilot/THIRD_PARTY.md` with `python3 tools/dataset/third_party.py`.
  `--check` fails when the file is out of date or when `third_party.json` no
  longer matches the tasks. Do not edit `THIRD_PARTY.md` by hand.
- **Keep the manifest current.** `datasets/pilot/manifest.json` records every
  task and a checksum of every file in its folder, and the CLI, the catalog and
  the web UI read it. After you change a task, run `uv run ssebench dataset
  manifest`; `uv run ssebench dataset manifest --check` fails when it is stale.
  Do not edit it by hand.
- **Version the dataset.** Change `version` in `datasets/pilot/dataset.yaml`,
  for example from `pilot-v1` to `pilot-v2`, when tasks are added or removed, or
  changed in a way that can change their results. A fix to a typo does not need
  a new version. [Dataset manifest](docs/dataset/manifest.md) describes the
  files.
- **Keep the licenses straight.** The task material you write (configuration,
  scripts, PoCs, reports and tests) is CC BY 4.0. Upstream code, patches and
  tests that a task includes keep the license of their project, and stay
  attributed to it.
- **Change the schema, not just the data.** The task config is defined by the
  models in `bench/src/ssebench/tasks/`. `uv run ssebench dataset schema`
  regenerates `datasets/schema/`, and `just docs-check` fails when it is stale.

## Pull requests

1. For anything larger than a small fix, open an issue first so we can agree on
   the approach.
2. Fork the repository and branch from `main`. Keep each pull request focused
   on one change.
3. Write commit messages as `type(scope): description`, for example
   `feat(catalog): make the listen port configurable`. Types: `feat`,
   `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `style`. The
   scope is the component.
4. Add or update tests, and update `docs/` when behaviour visible to users
   changes.
5. If you used AI tools to write the change, say so in the pull request
   description, or add an `Assisted-by:` trailer naming the tool and model.
6. Make sure `just lint`, `just test` and `just docs-check` pass, and that
   `bun run docs:build` does if you changed `docs/`. Commit what
   `just docs-gen`, `ssebench dataset manifest` and
   `python3 tools/dataset/third_party.py` regenerate.
7. Open the pull request against `main`. CI runs on it; fix real failures with
   new commits. A maintainer reviews every pull request, and merges it by
   rebasing, so `main` keeps a linear history of focused commits.

Never include API keys, `.env` files or run results in a pull request.

## License of contributions

There is no contributor license agreement. By submitting a contribution you
agree that it is licensed under the [Apache License 2.0](LICENSE), as its
section 5 describes. Task material in `datasets/pilot/` is licensed under
[CC BY 4.0](datasets/pilot/LICENSE); upstream code included in a task keeps its
own license.
