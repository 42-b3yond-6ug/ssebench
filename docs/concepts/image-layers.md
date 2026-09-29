---
outline: deep
---

# Image layers

The container image for a run is built in four layers, each one a Docker image
built on top of the one before it. The code that chains them is
`ssebench.pipe.build_pipe`: each layer receives the image name of the previous
layer and returns its own.

```
base      $SSEBENCH_REGISTRY/base-generic-go:1.0.0               toolchain, per language
  |
case      $SSEBENCH_REGISTRY/case/pilot/gjson-196-bf4efcb        project + task files, per task
  |
tool      $SSEBENCH_REGISTRY/tool/gjson-196-bf4efcb:<version>    SSEBench runtime, per task
  |
agent     $SSEBENCH_REGISTRY/agent-dummy/gjson-196-bf4efcb:<version>
                                                                 agent under test, per agent and task
```

This is sandbox mode, the default. Sidecar mode builds its tool layers
differently; see [below](#sidecar-mode).

## The layers

| Layer | Built from | Image name | Built by |
|---|---|---|---|
| Base | `images/base-images/generic-{c,go,rust}/Dockerfile` | `base-generic-<lang>:<version>` and `:latest` | `just base-images`, or `make -C images/base-images <name>` |
| Case | the task's `Dockerfile` | `case/<dataset>/<task-id>`, lowercase, untagged | `ssebench run --local`, `ssebench build-case`; or pulled from a catalog |
| Tool | `images/sandbox/Dockerfile` | `tool/<task-id>:<version>` | `ssebench run` |
| Agent | `agents/<name>/Dockerfile` | `agent-<name>/<task-id>:<agent version>`, lowercase | `ssebench run` |

Every name is prefixed with `$SSEBENCH_REGISTRY/` (default
`ghcr.io/42-b3yond-6ug/ssebench`). `<version>` is the SSEBench version in
`VERSION`, which `ssebench --version` prints.

### Base

The toolchain for one language, shared by every task in that language:
`generic-c` (Clang, LLVM with the sanitizer runtimes, CMake, autotools, gdb),
`generic-go` (Go) and `generic-rust` (Rust through rustup, and the C
toolchain). Each also has git, curl and uv. The Makefile tags each image with
the SSEBench version and with `latest`, and a local build also with every
version that a dataset manifest names. Task Dockerfiles pin the base images of
a release, such as `base-generic-go:1.0.0`; see
[Base images](/dataset/manifest#base-images).

`ssebench run` does not build base images: Docker pulls the one a task pins
when it builds the case image, unless you built it first with
`just base-images`.

### Case

One image per task, from the `Dockerfile` in the task folder. It declares
`ARG SSEBENCH_REGISTRY` and starts `FROM ${SSEBENCH_REGISTRY}/base-...:<version>`,
so the CLI builds it with `--build-arg SSEBENCH_REGISTRY=$SSEBENCH_REGISTRY`.
It contains:

- the project's source at the vulnerable commit, at the task's `source` path;
- whatever the project needs to build and test offline, such as vendored Go
  modules or fetched crates;
- the task files, copied from `sse/` to `/ssebench`: the config, the scripts,
  the reports, the proofs of concept and the diffs.

See [Tasks and datasets](/concepts/tasks-and-datasets). With `--local`, the CLI
runs the build on every run and Docker's build cache makes repeats fast;
`ssebench build-case` skips tasks whose image exists unless you pass
`--force`. Tasks from a catalog are pulled instead.

### Tool

The SSEBench runtime, added to the case image by `images/sandbox/Dockerfile`.
The CLI passes the case image as the `case-image` build context and the task's
`source` path as the `SOURCE_DIR` build argument; the build context is the
SSEBench home. The Dockerfile compiles the runtime in separate stages and then,
on top of the case image:

1. moves the project source to `/ssebench-repo` and makes it and `/ssebench`
   readable by root only;
2. copies the source back to `SOURCE_DIR`, owned by uid 1000;
3. runs `images/common/setup-source.sh`, which creates the user `model`
   (uid 1000) fresh with no supplementary groups, removing a base image's
   uid-1000 user (such as `ubuntu`) if one clashes; creates the unprivileged
   `sse-runner` user the daemon runs task scripts as; removes world-writable
   bits from files a check must not change; deletes every `.git` directory in
   the source and commits the tree again as a single commit, `buggy commit`;
4. adds the runtime:

| Path | Component |
|---|---|
| `/usr/local/bin/entrypoint` | The entrypoint (`runtime/entrypoint`, Go), the image's `ENTRYPOINT` |
| `/ssebench/ssebench-daemon` | The daemon (`sdk/daemon`, Rust): builds, PoCs and tests |
| `/ssebench/mcp` | The [MCP server](/reference/mcp-server) (`runtime/mcp`) with its virtual environment |
| `/evaluator` | The evaluator (`runtime/evaluator`) with its virtual environment |
| `/usr/local/bin/opencode` | The OpenCode server, which the entrypoint starts when present |

Steps 1 to 3 are what keep the answer away from the agent; see the
[integrity model](/concepts/integrity).

The daemon and the entrypoint are compiled from source into a stage named
`runtime`, laid out like the published `runtime` image. To take them from that
image instead of compiling them, build with
`--build-context runtime=docker-image://$SSEBENCH_REGISTRY/runtime:<version>`;
see [Releasing](/contributing/releasing#images).

An installed extension can provide another tool layer, selected with
`ssebench run --tool-layer NAME`; see
[Extension points](/guides/extension-points#tool-layers). The run summary
records the layer as `config.tool_layer`.

### Agent

The agent under test, from `agents/<name>/`. `agent.yaml` names the agent and
may set its image version, which defaults to the SSEBench version. The
Dockerfile starts `FROM ssebench-agent`, a build context that the CLI points at
the tool image; a second build context, `workspace`, is the SSEBench home, so
agent wrappers can install the SDK from it:

```dockerfile
FROM ssebench-agent
CMD ["echo dummy_QAQ"]
```

The image's `CMD` is the agent command. The entrypoint receives it as its
arguments and runs it as `model`. See [Add an agent](/guides/add-an-agent).

## When images are rebuilt

`ssebench run` asks Docker to build the case (with `--local`), tool and agent
images on every run. Docker's build cache makes this quick after the first
run, and a change to a task folder, to the runtime sources or to an agent's
files rebuilds only the layers above it. The first run of a task takes longest:
it builds the case image and compiles the runtime.

The tool and agent images carry the task ID in their names, so each task has
its own. They are tagged with the SSEBench version, so images from different
versions sit side by side.

## Using another registry

`SSEBENCH_REGISTRY` sets the prefix of every image SSEBench builds or pulls:
the base images (`make` reads it too), the case images and their `FROM` lines,
the tool, agent and [LiteLLM proxy](/concepts/litellm-proxy) images. To keep
your builds apart from the published images, set it to a local prefix, for
example in `.env`:

```sh
SSEBENCH_REGISTRY=localhost:5000/ssebench
```

With a catalog, case images are pulled from this prefix, so it must hold them.

## Sidecar mode

In sidecar mode the agent and the project run in separate containers, and two
images replace the tool and agent layers above:

- `tool-sidecar/<task-id>:<version>`, from `images/sidecar-case/Dockerfile` on
  the case image: the project and the daemon;
- `tool-sidecar-agent:<version>`, from `images/sidecar-agent/Dockerfile`, with
  no case image below it, and the agent image built on top of it,
  `agent-<name>/sidecar:<agent version>`: the agent, the MCP server and the
  evaluator. It does not depend on the task, so every task shares it.

`--tool-layer` does not apply. See [Sandbox and sidecar](/concepts/sandbox-and-sidecar).

## Next steps

- [Architecture](/concepts/architecture): how the layers fit into a run
- [Integrity model](/concepts/integrity): the protections the tool layer sets up
- [Extension points](/guides/extension-points): the image contract for custom tool layers
