# SSEBench

SSEBench measures how well AI coding agents fix real security vulnerabilities.

Every task is a publicly disclosed bug in an open-source C, Go or Rust project,
paired with its upstream fix. SSEBench drops an agent into a Docker container
with the vulnerable source tree and a small tool API for building and testing,
lets it work until it stops or times out, and then grades the patch it leaves
behind: does the project still build, does the proof-of-concept stop
reproducing, and do the project's tests pass, including the tests that came
with the upstream fix?

Agents and models are decoupled. Any agent can run against any model, because
all LLM traffic goes through a LiteLLM proxy.

[Quickstart](docs/getting-started/quickstart.md) ·
[Try the demo](docs/getting-started/demo.md) ·
[Documentation](docs/) ·
[The pilot dataset](docs/dataset/pilot.md) ·
[Contributing](CONTRIBUTING.md)

## What's inside

- **The `ssebench` CLI** builds the container images for a task and runs one
  agent × model × task combination, collecting logs, a snapshot of the final
  source tree and a graded `result.json`. It also checks your host
  (`ssebench doctor`), lists the tasks, and runs the local demo. It is on PyPI
  and runs without a clone of this repository.
- **A container runtime.** A Go entrypoint orchestrates a Rust daemon (build,
  PoC and test actions), an MCP server that gives the agent a `test_patch` tool,
  the agent itself and the evaluator.
- **Agents:** Claude Code, Codex, OpenCode, a no-op `dummy` agent for
  testing the pipeline, and a `reference` agent that applies each task's known
  fix, to check a task without a model.
- **Models:** LiteLLM model definitions for Anthropic, OpenAI and Google models.
  Adding a provider or model is a YAML change.
- **The `pilot` dataset:** 55 tasks (27 Go, 20 C, 8 Rust).
- **A web UI** for launching runs and watching them live: the agent dialog, the
  diff, a terminal into the container, and the evaluation result.
- **A task catalog service**, a Python SDK (`sse`) for code running inside task
  containers, and plugins that hook into the agent and grading phases.

## How it works

Each run happens in a container image assembled from four layers:

```
base    toolchain for the task's language (generic-c, generic-go, generic-rust)
└─ case     the project at the vulnerable commit, with its build dependencies
   └─ tool      the SSEBench runtime: entrypoint, daemon, SDK, MCP server, evaluator
      └─ agent     the agent under test
```

The tool layer comes in two variants. In **sandbox** mode (the default), the
agent runs in the same container as the project. In **sidecar** mode
(experimental), the agent runs in a separate container: it edits the project's
source through a shared volume, and builds and tests it only through the
daemon in the task container.

```mermaid
flowchart LR
    cli["ssebench CLI"]
    proxy["LiteLLM proxy"]
    providers["model providers"]
    results[("results/")]

    subgraph box["Task container"]
        entry["entrypoint (Go)"]
        agent["agent"]
        evaluator["evaluator"]
        mcp["MCP server<br/>test_patch"]
        daemon["ssebench-daemon (Rust)<br/>build, PoC and test actions"]
    end

    cli -- "build layers,<br/>start container" --> entry
    entry -- "runs" --> agent
    entry -- "then grades with" --> evaluator
    agent -- "MCP" --> mcp
    mcp --> daemon
    evaluator --> daemon
    agent -- "LLM calls" --> proxy
    proxy --> providers
    evaluator -- "result.json, logs,<br/>source snapshot" --> results
```

Inside the container, the entrypoint:

1. starts the daemon, which serves build, PoC and test actions over a Unix
   socket and HTTP;
2. starts the MCP server, whose `test_patch` tool lets the agent check its
   work, limited by the difficulty level;
3. runs the agent as an unprivileged user with the task description (the issue
   or crash report), until it exits or hits the timeout;
4. runs the evaluator, which applies the agent's changes to a clean tree and
   grades them: build, every PoC, the functional tests, and the intent tests
   (the upstream tests that accompany the fix) where the task has them.

Keeping the answer away from the agent is part of the design. The reference
patch and hidden tests are readable only by root, the agent runs as an
unprivileged user, and the project's git history is replaced by a single commit
so the fix cannot be recovered from `git log`. Any way around this is a
security bug; see [SECURITY.md](SECURITY.md).

### Difficulty levels

The difficulty level decides which checks `test_patch` runs for the agent while
it works. Final grading always runs every check the task has.

| Level | Name | `test_patch` runs |
|---|---|---|
| 0 | `FULL_ASSISTANCE` | build, functional tests, PoC, intent tests |
| 1 | `NO_INTENT_TEST` | build, functional tests, PoC |
| 2 | `NO_FUTURE_TEST` (default) | build, functional tests |
| 3 | `BUILD_ONLY` | build |
| 4 | `NO_BUILD` | nothing |

## Quickstart

You need Docker with the buildx and Compose plugins, and
[uv](https://docs.astral.sh/uv/); [just](https://just.systems/) if you work
from a clone. An x86-64 Linux host is recommended: the pilot tasks are
amd64-only, so an arm64 host runs them under emulation, which is slow. Images
take tens of GB. See [Installation](docs/getting-started/installation.md).
macOS with Docker Desktop is untested; its requirements and caveats are in
[Installation](docs/getting-started/installation.md#macos-and-docker-desktop).

**See it work, with no API key**

```sh
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
just setup    # install dependencies and write .env with generated local secrets
just demo     # apply the known fix to a pilot task, grade it, and open the run in the web UI
just demo-down
```

`just demo` starts the LiteLLM proxy, the task catalog and the web UI with
Docker Compose, runs the `reference` agent, which applies the task's upstream
fix instead of asking a model, and prints the address of the web UI,
`http://127.0.0.1:3001`, where the run is open: the dialog, the diff and the
evaluation result. See [Try the demo](docs/getting-started/demo.md).

**Run a real agent, without a clone**

```sh
mkdir ssebench-work && cd ssebench-work
uvx ssebench init          # writes .env with generated secrets, models/ and results/
```

Add your provider key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or
`GOOGLE_API_KEY`) to `.env`, then:

```sh
uvx ssebench doctor        # checks Docker, disk space, .env and the provider keys
uvx ssebench tasks list    # the 55 tasks of the pilot dataset
uvx ssebench run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

From a clone, `just run --task gjson-196-bf4efcb --agent claude-code --model
claude-sonnet-4-6` does the same, and `just run` alone opens interactive
pickers. Each run writes `results/<task>/<model>/<agent>/<run-id>/`, so repeated
runs keep their results: `summary.json`, `result.json` (the grade), the agent
dialog (`archive/dialog.jsonl`), a snapshot of the final source tree, and the
logs of every component.

A real run calls a model with your key and costs money. When something does not
work, start with `ssebench doctor` and
[Troubleshooting](docs/getting-started/troubleshooting.md). The
[Quickstart](docs/getting-started/quickstart.md) walks through all of this and
explains how to read the results.

## Repository map

| Path | What it is |
|---|---|
| `bench/` | The `ssebench` CLI (package `ssebench`): builds image layers and runs agent × model × task. |
| `runtime/entrypoint/` | Container entrypoint (Go). Starts the daemon, MCP server, agent and evaluator. |
| `runtime/evaluator/` | Grades the final state of the source tree. |
| `runtime/mcp/` | MCP server exposing `test_patch`. |
| `runtime/plugins/` | Plugins that run before, during or after the agent and grading phases. |
| `sdk/daemon/` | `ssebench-daemon` (Rust): build, PoC and test actions over a Unix socket and HTTP. |
| `sdk/python/` | `ssebench-sdk`, imported as `sse`: the Python client used inside task containers. |
| `images/` | Base images (`generic-c`, `generic-go`, `generic-rust`), the LiteLLM proxy image, the runtime image, and the sandbox and sidecar tool layers. |
| `agents/` | Agent layers: `claude-code`, `codex`, `opencode`, `dummy`, `reference`. |
| `models/` | LiteLLM model definitions, one file per provider. |
| `catalog/` | Task catalog service (Go). |
| `webui/` | Web UI: Vite + React front end, Bun/Hono server, and `pty-proxy` (Go) for terminals. |
| `datasets/pilot/` | The pilot dataset, one folder per task, with its manifest. |
| `datasets/schema/` | JSON Schemas of the task config, `dataset.yaml` and the manifest. |
| `tools/bear/` | Generates `compile_commands.json` for C tasks. |
| `tools/dataset/` | Generates `datasets/pilot/THIRD_PARTY.md` from the task configs and `third_party.json`. |
| `tools/docs/` | Regenerates the reference pages in `docs/reference/` from the code, and checks them for drift. |
| `tools/release/` | Sets the version of every component and checks for drift. |
| `tools/report/` | Typst report built from `results/`. |
| `tests/` | End-to-end smoke run, the integrity bypass suite, and the offline test of every agent. |
| `docs/` | Documentation site (VitePress). |
| `deploy/compose/` | Docker Compose stack: the LiteLLM proxy and its database, and the demo's catalog and web UI. |
| `Justfile`, `just/` | The recipes: `just` lists them. |
| `flake.nix`, `nix/` | Optional Nix flake: development shell, packages, checks and formatter. |
| `.github/` | CI and release workflows (GitHub Actions), issue and pull request templates. |
| `pyproject.toml`, `Cargo.toml`, `go.work`, `package.json`, `VERSION` | Roots of the Python (uv), Rust, Go and Bun workspaces, and the one version every component shares. |

Each top-level component has a README that says what it is and where to look
next; [Project structure](docs/contributing/project-structure.md) describes the
layout in more detail.

## Dataset

`datasets/pilot/` contains 55 tasks. Each one is a real vulnerability with a
public advisory or issue and an upstream fix.

| Language | Tasks | Projects | Typical bug classes |
|---|---|---|---|
| Go | 27 | Kubernetes, Open Policy Agent, Argo Workflows, gin, Fiber, gjson, go-yaml, jwt-go, gnark-crypto, … | injection, authentication bypass, path traversal, denial of service, out-of-range panics |
| C | 20 | CPython, libxml2, Vim, PHP, QuickJS, jq, libtiff, exiv2, WABT, Wireshark | heap and stack buffer overflows, use-after-free, NULL dereference (AddressSanitizer) |
| Rust | 8 | smallvec, http, string-interner, nano-arena, stack_dst, ammonia, nano-id | memory safety in `unsafe` code, cross-site scripting, weak randomness |

A task folder holds a `Dockerfile` for its case image and an `sse/` directory:
`config.yaml` (task metadata), `build.sh`, `run.sh` and `test.sh`, the PoC
inputs, the issue or crash report the agent receives, and the reference patch
and tests used for grading.

The dataset version is `pilot-v1`. `datasets/pilot/manifest.json` lists every
task with its metadata and a checksum of each of its files; the CLI, the task
catalog and the web UI read it, and `ssebench tasks list` prints it. Task
images are built from the folders, or pulled from the registry. Every task
records its upstream project, license, advisory and fix in
`datasets/pilot/THIRD_PARTY.md`. See [The pilot dataset](docs/dataset/pilot.md)
and [Dataset manifest](docs/dataset/manifest.md).

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), and
please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security
issues, including ways for an agent to reach the reference answer, privately
as described in [SECURITY.md](SECURITY.md).

## Contributors

SSEBench was built by (in alphabetical order by family name):

- [Dang (midas) Le](https://github.com/lkmidas)
- [Nguyễn Anh Khoa](https://github.com/nganhkhoa)
- [Wenxuan Shi](https://github.com/whexy)
- [Xinyu Xing](https://github.com/xxy83)
- [Dongpeng Xu](https://github.com/dongpengxu)

## Citation

If you use SSEBench in your research, please cite it:

```bibtex
@misc{ssebench,
  title        = {SSEBench},
  author       = {{The SSEBench authors}},
  year         = {2026},
  howpublished = {\url{https://github.com/42-b3yond-6ug/ssebench}}
}
```

## License

- Code is licensed under the [Apache License 2.0](LICENSE). See also
  [NOTICE](NOTICE).
- Task material written for the pilot dataset (configurations, scripts, PoCs,
  reports and tests) is licensed under
  [CC BY 4.0](datasets/pilot/LICENSE).
- Upstream source code, patches and tests included in the dataset keep their
  original licenses; see [THIRD_PARTY.md](datasets/pilot/THIRD_PARTY.md).
