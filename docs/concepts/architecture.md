---
outline: deep
---

# Architecture

SSEBench runs every agent × model × task combination in Docker, from images
built in layers. This page is the overview; the other concept pages go into
detail.

## System overview

```
ssebench CLI
   |  builds the image layers, creates a key for the run,
   |  starts the container
   v
+-- task container --------------------------------------------+
|  the entrypoint starts, in order:                            |
|    1. ssebench-daemon   build, PoC and test actions          |
|    2. MCP server        the test_patch tool                  |
|    3. agent             runs as the unprivileged user model  |
|    4. evaluator         grades the final source tree         |
+--------------------------------------------------------------+
   |                                    |
   |  result.json, dialog.jsonl,        |  LLM requests
   |  logs, source snapshot             |  from the agent
   v                                    v
results/                           LiteLLM proxy ---> model providers
```

## Docker image layers

The image for a run is built from four [layers](/concepts/image-layers), each
on top of the previous one.

### Base image

The toolchain for the task's language, shared by every task in that language:

- `generic-c`: compilers, LLVM and the usual C build tools;
- `generic-go`: the Go toolchain;
- `generic-rust`: the Rust toolchain;

plus git and common build utilities. The base images are defined in
`images/base-images/`.

### Case image

One per task, built from the `Dockerfile` in the task's folder:

- the project's source code at the vulnerable commit;
- its build dependencies;
- the task's files: its metadata, the build, run and test scripts, the
  proof-of-concept inputs, the report the agent receives, and the reference
  patch and tests used for grading.

### Tool image

The SSEBench runtime, added on top of the case image:

- the **entrypoint**, which starts and supervises everything else in the
  container;
- **`ssebench-daemon`**, which builds the project and runs its proofs of
  concept and tests, over a Unix socket and HTTP;
- the **Python SDK** (`sse`), which the other components use to talk to the
  daemon;
- the **MCP server**, which gives the agent the
  [`test_patch`](/reference/mcp-server) tool;
- the **evaluator**, which grades the result.

There is one tool layer for each [running mode](#running-modes).

### Agent image

The agent under test, built from the `Dockerfile` in `agents/<name>/` on top of
the tool layer: the agent itself and its configuration. The bundled agents also
include a wrapper that starts the agent with the task and records its session.

All images are named under one registry prefix, set with `SSEBENCH_REGISTRY`.

## LiteLLM proxy

Agents never talk to a model provider directly. Every LLM request goes through
a [LiteLLM proxy](/concepts/litellm-proxy) that runs next to the task
containers:

```
agent  --->  LiteLLM proxy  --->  model provider (Anthropic, OpenAI, Google, ...)
```

- **Any agent, any model.** The proxy serves both OpenAI-style and
  Anthropic-style APIs, so each agent uses its own client and the model is
  chosen by name.
- **One key per run.** Before each run, the CLI creates a proxy key that can
  use only the selected model, with a spending limit.
- **Cost tracking.** The spend of each run's key is recorded with its result.

The models the proxy offers are defined in `models/*.yaml`; see
[Add a model](/guides/add-a-model).

## Running modes

### Sandbox mode

The agent and the project run in the **same container**. This is the default.

```
+-- task container ----------------------+
|  agent  <-- edits, builds -->  project |
+----------------------------------------+
```

- The agent works on the project's files directly, with the task's toolchain
  at hand.
- **Use when** the agent can run in the task's environment, which is the case
  for the bundled agents.

### Sidecar mode

The agent and the project run in **separate containers**:

```
+-- agent container ---+          +-- task container ---+
|  agent               |          |  ssebench-daemon    |
|  MCP server          | <------> |  project toolchain  |
|  evaluator           |          |  task files         |
+----------------------+          +---------------------+
     \___ shared volumes: the source tree, the daemon's sockets ___/
```

- The source tree is shared between the two containers through a Docker
  volume. The agent edits the files directly, but builds and tests run in the
  task container, through the daemon. The task's files, including the
  reference patch, stay in the task container.
- **Use when** the agent needs dependencies that conflict with the task's
  environment, or to build one agent image for every task.

Sidecar mode is experimental. See [Sandbox and sidecar](/concepts/sandbox-and-sidecar).

## What happens during a run

1. **Select.** You choose a task, an agent, a model, a mode and a difficulty
   level.
2. **Prepare.** The CLI starts the LiteLLM proxy if needed, creates a key for
   the run, and builds the image layers.
3. **Start.** The task container starts. The entrypoint starts the daemon and
   the MCP server.
4. **Work.** The agent runs as the user `model` with a prompt built from the
   task's report and scripts, until it stops or reaches the timeout.
5. **Check.** While it works, the agent may call `test_patch` to build and test
   its changes, within the limits of the
   [difficulty level](/concepts/difficulty-levels).
6. **Grade.** The evaluator applies the agent's changes to a clean copy of the
   project and runs every check the task has. See
   [Grading pipeline](/concepts/grading).
7. **Collect.** The grade, the agent's dialog, a snapshot of the source tree
   and the logs are written to `results/`, along with a summary of the run.
   See [Results format](/concepts/results).

## Benchmark integrity

The agent must not be able to find the answer instead of working it out. The
[integrity model](/concepts/integrity) describes the protections in full; two
of them shape the container itself.

### User isolation

In sandbox mode, the agent runs as the unprivileged user `model` (uid 1000),
and the task's files are readable only by root:

```
Root only (the agent cannot read them):
  /ssebench/config.yaml        task metadata
  /ssebench/diffs/             reference patch and hidden tests
  /ssebench/pocs/              proof-of-concept inputs

Accessible to the agent:
  /src/<project>/              the project's source tree
  /home/model/                 the agent's home directory
  /tmp/sse-archive/            the run's results directory
```

The agent gets the task through its prompt, and `test_patch` runs the checks
on its behalf.

### Git history reset

When the image is built, every `.git` directory in the project, including
those of submodules, is removed, and the tree is committed again as a single
commit:

```
$ git log --oneline
abc1234 buggy commit
```

So the fix can't be recovered with `git log`, `git blame` or `git diff`
against a later commit.

## Next steps

- [Tasks and datasets](/concepts/tasks-and-datasets)
- [Image layers](/concepts/image-layers)
- [Grading pipeline](/concepts/grading) and [Results format](/concepts/results)
- [Integrity model](/concepts/integrity)
- [MCP server](/reference/mcp-server): the `test_patch` tool
- [Dialog protocol](/reference/dialog-protocol): how agents report their
  session to the web UI
- [Project structure](/contributing/project-structure): where each component
  lives
