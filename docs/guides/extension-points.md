---
outline: deep
---

# Extension points

Third parties can extend SSEBench from their own package, without forking
it:

- a **tool layer** changes the runtime image that the agent runs in, and is
  selected with `ssebench run --tool-layer NAME`;
- a **runner backend** changes where a run's containers execute, and is
  selected with `ssebench run --backend NAME`;
- a **command** adds a subcommand, `ssebench NAME`;
- a **container mode** changes how the entrypoint orchestrates the task
  container, and is selected with `entrypoint --mode NAME`.

A Python package registers tool layers, runner backends and commands as
[entry points](https://packaging.python.org/en/latest/specifications/entry-points/)
and imports everything it needs from `ssebench.extensions`. A Go program adds
container modes by importing the entrypoint as a library; a tool layer then
ships that program in the image. This page also lists the
[container contract](#container-contract): the environment variables,
sockets, ports, paths and labels that SSEBench keeps stable for extensions,
agents and plugins.

## Register an extension

Declare the entry points in the package's `pyproject.toml`. The entry-point
name is the name users type:

```toml
[project]
name = "my-ssebench-ext"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["ssebench"]

[project.entry-points."ssebench.tool_layers"]
example = "my_ssebench_ext:ExampleToolLayer"

[project.entry-points."ssebench.backends"]
logging = "my_ssebench_ext:LoggingBackend"

[project.entry-points."ssebench.commands"]
hello = "my_ssebench_ext:HelloCommand"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install the package into the environment that runs `ssebench`. From a clone
of SSEBench:

```sh
uv pip install /path/to/my-ssebench-ext
uv run ssebench --help            # lists the new command
```

`uv run` keeps the extension installed. `uv sync` removes packages that are
not in `uv.lock`, so install the extension again after it, or run
`uv sync --inexact`.

`bench/tests/fixtures/ssebench_example_ext` is a complete extension with the
tool layer, the backend and the command shown below. The tests in
`bench/tests/test_extensions.py` install it and use both.

| Group | Name selects | Object |
|-------|--------------|--------|
| `ssebench.tool_layers` | `ssebench run --tool-layer NAME` | a subclass of `ToolLayer` |
| `ssebench.backends` | `ssebench run --backend NAME` | a subclass of `Backend`, created without arguments |
| `ssebench.commands` | `ssebench NAME` | an object that implements `Command`, or a class whose instances do |

## Tool layers

A run's image is built from four [layers](/concepts/image-layers):
base, case, tool and agent. The tool layer adds the SSEBench runtime to the
case image: the entrypoint, the daemon, the MCP server, the evaluator and
OpenCode. The built-in layer is `sandbox` (`images/sandbox/Dockerfile`). An
extension can add another, for example one that installs more tools for the
agent or runs a different entrypoint.

```python
from ssebench.extensions import ToolLayer, ToolLayerContext
```

- `ssebench run` constructs the layer as `Layer(context)`. The base class
  stores the context as `self.context`.
- `ToolLayerContext` has these fields:
  - `task_name`: the task ID, for example `gjson-196-bf4efcb`;
  - `source_dir`: the absolute path of the project source in the case image;
  - `build_root`: the SSEBench home, which holds `images/`, `runtime/` and
    `sdk/` and is the build context of the built-in layers. Without a clone
    of the repository, it is the copy of these directories that `ssebench`
    carries. That copy has no sources of the daemon and the entrypoint, which
    the built-in layers take from the published `runtime` image instead; a
    layer that builds on `SandboxToolLayer`, as the example below does,
    needs no change;
  - `platform`: the `linux/<arch>` platform that the run builds and runs
    every image for, that of the case image, or `None` for the Docker host's
    own. Pass it as `--platform` to your `docker buildx build`, so that your
    layer has the architecture of the image below it.
- `docker_image(base)` gets the name of the case image, builds the tool image
  on top of it and returns the tool image's name. The agent image is then built
  from that image. The tool image must meet the
  [image contract](#image-contract).
- Build on `SandboxToolLayer` to keep the standard runtime. Name images like
  the built-in ones do, with `REGISTRY`, the image prefix that
  `SSEBENCH_REGISTRY` sets, and `TAG`, the SSEBench version that every
  component and image shares, so the images of two SSEBench versions do not
  replace each other.

This layer adds one Docker layer on top of the standard runtime:

```python
import subprocess
from typing import override

from ssebench.extensions import REGISTRY, TAG, SandboxToolLayer, ToolLayer

DOCKERFILE = """\
FROM runtime
LABEL org.example.tool-layer="example"
"""


class ExampleToolLayer(ToolLayer):
    @override
    def docker_image(self, base: str | None) -> str:
        runtime = SandboxToolLayer(self.context).docker_image(base)
        image = f"{REGISTRY}/tool-example/{self.context.task_name.lower()}:{TAG}"
        platform = ["--platform", self.context.platform] if self.context.platform else []
        subprocess.run(
            ["docker", "buildx", "build", *platform,
             "--build-context", f"runtime=docker-image://{runtime}",
             "-t", image, "--load", "-"],
            input=DOCKERFILE, text=True, check=True,
        )
        return image
```

Run it with:

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
  --agent dummy --model claude-sonnet-4-6 --tool-layer example
```

- `--tool-layer` applies to sandbox mode. Sidecar mode uses its own two
  layers and rejects the option.
- The run summary records the layer in `config.tool_layer`.
- Names are unique. `ssebench run` stops with an error that names every
  package involved if the selected name is registered more than once or is
  also a built-in name, and when the selected object cannot be imported or is
  not a `ToolLayer` subclass.
- Only the selected layer is imported.

## Runner backends

A backend carries out the run that the runner describes: it prepares the
images, starts the containers, streams their output, collects the results and
cleans up. The built-in backends are `docker` and [`kubernetes`](/deployment/kubernetes).
An extension can add one that runs the same run elsewhere. The
[Runner backends](/concepts/runner-backends) page specifies the run
specification and every method of the interface; this section shows how to
register one.

```python
from ssebench.extensions import Backend, DockerBackend, RunHandle, RunSpec
```

- `ssebench run --backend NAME`, or `SSEBENCH_BACKEND=NAME`, creates the class
  without arguments, once for the run.
- Subclass `Backend` and implement all of its methods, or subclass
  `DockerBackend` and override the ones you change.
- Set `builds_images = True` only if `prepare_images` can build the layers of a
  run. Otherwise `ssebench run` requires `--prebuilt`, and `prepare_images` only
  makes the [prebuilt images](/concepts/runner-backends#prebuilt-images)
  available. `prebuilt_images(request)` gives their names.

This backend announces each run and leaves the rest to Docker:

```python
from typing import override

from ssebench.extensions import DockerBackend, RunHandle, RunSpec


class LoggingBackend(DockerBackend):
    name = "logging"

    @override
    def start(self, spec: RunSpec) -> RunHandle:
        print(f"starting run {spec.run_id} of {spec.task_name} in {spec.mode} mode")
        return super().start(spec)
```

Run it with `uv run ssebench run --backend logging ...`.

## Commands

```python
from ssebench.extensions import Command
```

`Command` is a protocol with four members:

| Member | Description |
|--------|-------------|
| `name: str` | The subcommand; it must equal the entry-point name |
| `help: str` | One line, shown by `ssebench --help` |
| `configure(parser: argparse.ArgumentParser) -> None` | Adds the subcommand's arguments to `parser`; it may be called more than once |
| `run(args: argparse.Namespace) -> int` | Runs the subcommand and returns its exit status |

Register the class, which is instantiated without arguments, or an instance.

```python
import argparse
from typing import override

from ssebench.extensions import Command


class HelloCommand(Command):
    name = "hello"
    help = "Print a greeting"

    @override
    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--name", default="world", help="Who to greet")

    @override
    def run(self, args: argparse.Namespace) -> int:
        print(f"Hello, {args.name}!")
        return 0
```

```console
$ uv run ssebench hello --name SSEBench
Hello, SSEBench!
```

Commands are imported only when they can be used: for `ssebench --help`,
`ssebench` without a command, an unknown command, or the command itself. The
built-in commands (`run`, `build-case`, `dataset`, `tasks`, `proxy`, `doctor`)
import no extension. A command that cannot be imported, does not implement
`Command`, has a different `name`, fails in `configure`, is registered more
than once or has a built-in name is left out with a warning, and the rest of
the CLI keeps working.

## Container modes

The entrypoint is the Go package
`github.com/42-b3yond-6ug/ssebench/runtime/entrypoint/pkg/entrypoint`. The
default binary, `runtime/entrypoint/cmd/ssebench-entrypoint`, registers the
built-in modes, `sandbox` and `sidecar`, and calls `entrypoint.Main()`. Your
own `main` package can register more modes next to them:

```go
func main() {
	entrypoint.MustRegister(entrypoint.BuiltinModes()...)
	entrypoint.MustRegister(hello{})
	entrypoint.Main()
}
```

A mode implements `Mode`:

```go
type Mode interface {
	Name() string        // the value of --mode that selects it
	Run(rt *Runtime) int // orchestrates the container; returns the exit status
}
```

The package provides:

| Name | Description |
|------|-------------|
| `Register(modes ...Mode) error` | Adds modes; an empty or already registered name is an error |
| `MustRegister(modes ...Mode)` | Like `Register`, but panics on error |
| `Lookup(name string) (Mode, bool)`, `Modes() []string` | The registered modes |
| `Sandbox`, `Sidecar`, `BuiltinModes() []Mode` | The built-in modes; a mode can call `entrypoint.Sandbox.Run(rt)` to add steps around the standard run |
| `Main()` | Runs the entrypoint with the process arguments and exits |
| `Run(args []string) int` | The same, returning the exit status; for tests |
| `Version` | Printed by `--version` |
| `Configurer` | Optional interface with `Configure(cfg *Config)`, called before the `TIMEOUT`, `SSE_DAEMON_TIMEOUT` and `SSE_MCP_TIMEOUT` overrides; the sidecar mode uses it to read the daemon's socket from `SSE_DAEMON_SOCKET` and to move the MCP server and evaluator paths. See [Modes that own stdio or take no command](#modes-that-own-stdio-or-take-no-command) for the log and command fields |

Before `Run`, the entrypoint installs the SIGINT and SIGTERM handler, makes the
results directory (`SSE_RESULTS`) `0755` inside a root-only parent, so only
root in the container can reach it and write the grade and logs, and creates
the log files. It creates the agent's archive (`SSE_ARCHIVE`) if it is missing,
and gives it to the `model` user only when the mode leaves
`Config.AgentWritesArchive` set, which the built-in modes do; a mode where only
root writes clears it in `Configure`, and the archive stays root-owned. After
`Run` returns, it stops every service the mode started and exits with the
returned status. Inside `Run`, the mode uses the `*Runtime`:

| Method | Description |
|--------|-------------|
| `Config() Config` | Paths, sockets and timeouts of this run |
| `AgentCommand() []string` | The agent command, from the arguments after `--` |
| `Logger() *slog.Logger` | The entrypoint's logger, which writes to `Config.LogTo` |
| `LogPath(name string) string` | `<SSE_RESULTS>/<name>.log` |
| `StartDaemon() error` | Starts the daemon with its agent-facing and admin sockets |
| `WaitForDaemon() error` | Waits for a daemon in another container, as the sidecar mode does |
| `StartMCPServer() error` | Starts the MCP server and waits until it answers |
| `StartOpenCodeServer()` | Starts OpenCode on port 4096 if it is installed |
| `StartService(name string, argv []string, dir string, env []string) error` | Starts another background process, logged to `LogPath(name)` |
| `RunAgent() (AgentResult, error)` | Runs the agent as `model` with its time limit, then ends the agent phase; runs the agent-phase [plugins](/concepts/plugins-and-hooks#hooks) around it |
| `EndAgentPhase()` | Ends the agent phase; only the first call has an effect |
| `Evaluate(result AgentResult)` | Ends the agent phase, then grades through the admin socket and writes `result.json` to the results directory; runs the grading plugins around it |
| `KeepAlive()` | Blocks while `SSE_KEEP_ALIVE=1` keeps the container for the web UI |

`AgentResult` has the agent's `ExitStatus` (124 when it was killed at its time
limit), its `Duration` and `TimedOut`.

Ending the agent phase closes the daemon's tools to the agent-facing listeners
and kills the agent user's processes, so nothing the agent left running takes
part in grading. `RunAgent` ends it once the agent has exited, and `Evaluate`
ends it before grading at the latest. A mode whose agent does not run through
`RunAgent`, for example because it runs elsewhere, calls `EndAgentPhase` when
the agent is done, and never before. The reference patch is served only on the
admin socket, at any time.

### Modes that own stdio or take no command

By default the entrypoint writes its log to stdout, relays the daemon's and the
evaluator's logs there, and exits with a usage error when it gets no agent
command. A mode changes both in `Configure`, through two `Config` fields:

| Field | Default | Description |
|-------|---------|-------------|
| `LogTo LogDestination` | `LogToStdout` | Where the entrypoint's log and the relayed service logs go. `LogToStderr` writes them to stderr. `LogToFile` writes the entrypoint's log only to `entrypoint.log` in the results directory, relays no service log, and leaves stdout and stderr to the mode; until the results directory exists, it reports errors on stderr. |
| `AgentCommandOptional bool` | `false` | The mode runs without an agent command, so a missing one is not a usage error. `RunAgent` returns an error when there is no command to run. |

A mode that speaks a protocol over the container's stdin and stdout sets `LogTo`
to `LogToStderr` or `LogToFile`, so nothing but the protocol reaches stdout; the
entrypoint starts its services with no stdin and with their output in log files.
A mode that runs no agent sets `AgentCommandOptional`, and its image needs no
command after `--`.

Log files, in the results directory and under `plugins/`, are appended to and
never truncated, so a second run of the entrypoint in the same container keeps
what the first one wrote. The relay of a service's log starts at the point where
that run's output begins.

```go
func (stdio) Configure(cfg *entrypoint.Config) {
	cfg.LogTo = entrypoint.LogToFile
	cfg.AgentCommandOptional = true
	cfg.AgentWritesArchive = false
}
```

`runtime/entrypoint/examples/stdio-mode` is a complete program with such a mode,
`stdio`, which answers each line on stdin with `echo: ` and the line. Its test
starts the entrypoint as a process and checks that stdout holds only the answers.

### An example mode

This mode greets and writes the agent command to `hello.txt` in the results
directory, without starting anything:

```go
type hello struct{}

func (hello) Name() string { return "hello" }

func (hello) Run(rt *entrypoint.Runtime) int {
	command := strings.Join(rt.AgentCommand(), " ")
	rt.Logger().Info("Hello from a registered mode", "command", command)

	path := filepath.Join(rt.Config().ArchivePath, "hello.txt")
	if err := os.WriteFile(path, []byte("hello: "+command+"\n"), 0o644); err != nil {
		rt.Logger().Error("Failed to write hello.txt", "err", err)
		return 1
	}
	return 0
}
```

`runtime/entrypoint/examples/hello-mode` is the complete program, in its own
module, with a test. Its `go.mod` points the entrypoint module at a local
checkout:

```
require github.com/42-b3yond-6ug/ssebench/runtime/entrypoint v0.0.0

replace github.com/42-b3yond-6ug/ssebench/runtime/entrypoint => ../..
```

To use a mode in runs, a [tool layer](#tool-layers) builds the program on top
of the standard runtime and makes it the entrypoint, with the mode selected:

```dockerfile
FROM golang:1.26-bookworm AS builder
COPY . /build
WORKDIR /build
RUN CGO_ENABLED=0 go build -o /entrypoint .

FROM runtime
COPY --from=builder /entrypoint /usr/local/bin/entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint", "--mode", "hello", "--"]
```

## Container contract

Agents, plugins and tool layers rely on the items below. They change only
together with the runtime, the SDK, the agents and this page.

### Image contract

A tool image, and so each agent image built from it, must:

- have the entrypoint as its `ENTRYPOINT`. It receives the agent command,
  which is the agent image's `CMD`, as its arguments, runs it as the user
  `model` (uid 1000) and exits with the agent's exit status, or 124 when the
  agent timed out;
- write the grade to `result.json` in the results directory (`SSE_RESULTS`)
  before it exits (the evaluator does this);
- keep the paths below. An agent Dockerfile builds on the tool image with
  `FROM ssebench-agent`; `ssebench run` passes the tool image as the
  `ssebench-agent` build context.

| Path | Contents |
|------|----------|
| `/usr/local/bin/entrypoint` | The container entrypoint (`runtime/entrypoint`) |
| `/ssebench/ssebench-daemon` | The daemon (`sdk/daemon`) |
| `/ssebench/mcp` | The MCP server (`runtime/mcp`) and its virtual environment |
| `/evaluator` | The evaluator (`runtime/evaluator`) and its virtual environment |
| `/plugins` | `plugins.yaml`, its schema and the plugins the run selected, each with its virtual environment; root-owned. `Config.PluginsDir` points elsewhere. |
| `/ssebench` | The task's scripts and files from the case image; root only, except the build and test scripts and their support directories, which `sse-runner` may read and run |
| `/ssebench-repo` | The original project source; root only |
| `source_dir` from the task's `config.yaml` | The project source, owned by `model`, with its git history replaced by one commit |
| `/var/lib/ssebench/results` | The run directory (`SSE_RESULTS`), bind-mounted root-only from the host; the grade and the logs go here |
| `/tmp/sse-archive` | The agent's archive (`SSE_ARCHIVE`), the run directory's `archive/` bind-mounted from the host, owned by `model` |
| `/var/lib/ssebench-runner` | The task runner's scratch copies; `sse-runner` and root only |
| `/reference/patch.diff` | The task's reference patch, bind-mounted read-only for the `reference` agent and no other; see [Reference runs](/reference/cli#reference-runs) |

In the sidecar agent image the MCP server is in `/mcp`. The project source
and the daemon's sockets come from the environment container through shared
volumes; `/ssebench`, `/ssebench-repo` and the daemon stay in the environment
container. See [Sandbox and sidecar](/concepts/sandbox-and-sidecar#sidecar-mode).

### Environment variables

`ssebench run` sets these in the task container. In sidecar mode, the agent
container gets them all except `SSE_KEEP_ALIVE`, and the environment container
gets `SSE_ARCHIVE`, `SSE_RESULTS`, `SSE_DAEMON_SOCKET`, `SSE_DIFFICULTY` and
`SSE_KEEP_ALIVE`.

| Variable | Value |
|----------|-------|
| `SSE_API_KEY` | The run's LiteLLM key, which can use only the selected model |
| `SSE_BASE_URL` | The LiteLLM proxy, `http://litellm:4000` |
| `SSE_MODEL_NAME` | The selected model, as named in `models/*.yaml` |
| `SSE_ARCHIVE` | The agent's archive directory, `/tmp/sse-archive` |
| `SSE_RESULTS` | The root-only results directory, `/var/lib/ssebench/results` |
| `SSE_DIFFICULTY` | The [difficulty level](/concepts/difficulty-levels), from 0 to 4 |
| `TIMEOUT` | The agent's time limit in seconds (`--timeout`); the evaluator uses the same limit |
| `SSE_KEEP_ALIVE` | `1` keeps the container running after the run (`--keep-container`), otherwise `0` |
| `SSE_DAEMON_SOCKET` | Sidecar mode only: the daemon's agent-facing Unix socket, `/run/ssebench/sse.sock` |

A [reference run](/reference/cli#reference-runs) uses no model:
`SSE_MODEL_NAME` is `none`, and `SSE_API_KEY` and `SSE_BASE_URL` are empty.

The components in the container read these, with these defaults. The table is
generated from the [environment variable registry](/reference/environment).

<!-- generated: env container and runtime -->

| Variable | Default | Used by | Description |
|---|---|---|---|
| `SSE_API_KEY` | set by `ssebench run` | agents, plugins, sse.ai | The run's LiteLLM key, which can use only the selected model; empty in a reference run. |
| `SSE_BASE_URL` | set by `ssebench run` | agents, plugins, sse.ai | URL of the LiteLLM proxy, `http://litellm:4000`; empty in a reference run. |
| `SSE_MODEL_NAME` | set by `ssebench run` | agents, plugins, sse.ai | The selected model, as named in `models/*.yaml`; `none` in a reference run. |
| `SSE_ARCHIVE` | `/tmp/sse-archive` | entrypoint, daemon, evaluator, agents | The agent's archive directory, `/tmp/sse-archive`, writable by the agent: `dialog.jsonl` and whatever the agent side writes go there. The entrypoint requires it. The graded outputs go to `SSE_RESULTS` instead, root-only. |
| `SSE_RESULTS` | `/var/lib/ssebench/results` | entrypoint, daemon, evaluator | The run's results directory, root-only: the grade (`result.json`), the graded patch (`final.patch`), the commit log and the run's logs. Its parent is made `0700` root, so neither the agent nor the task runner can reach it. The CLI mounts the run directory here and its `archive/` subdirectory at `SSE_ARCHIVE`. Falls back to `SSE_ARCHIVE` when unset. |
| `SSE_DIFFICULTY` | `2` | daemon, MCP server | The [difficulty level](/concepts/difficulty-levels), from 0 to 4. The MCP server decides from it which checks `test_patch` runs, and the daemon refuses the withheld `bencher` actions on its agent-facing listeners. |
| `TIMEOUT` | `14400` in the entrypoint, `1800` in the evaluator | entrypoint, evaluator, agents | How long the agent may run, in seconds (`--timeout`). The evaluator uses the same limit for grading. |
| `SSE_KEEP_ALIVE` | `0` | entrypoint | `1` keeps the container running after grading (`--keep-container`), for the web UI. |
| `SSE_PLUGINS` | the plugins `plugins.yaml` enables | entrypoint | Comma-separated plugins to run, set by `ssebench run --plugin`; when it is set, it replaces the `enabled` field of `plugins.yaml`, and an empty value runs none. See [Plugins and hooks](/concepts/plugins-and-hooks). |
| `SSE_DAEMON_SOCKET` | `/tmp/sse.sock` | entrypoint, daemon, SDK | The daemon's agent-facing Unix socket, mode `0666`. The entrypoint sets it for every process it starts; in sidecar mode `ssebench run` sets it to `/run/ssebench/sse.sock`, on a root-owned volume the two containers share. Without it, the daemon serves HTTP only. |
| `SSE_ADMIN_SOCKET` | `/run/ssebench/admin.sock` | entrypoint, daemon | The daemon's privileged Unix socket, mode `0600`, root only: grading, the reference patch and phase changes. In sidecar mode it is on the volume the two containers share, and the task container's entrypoint sets it. The daemon binds it only when this is set; the entrypoint sets it, and points the evaluator's `SSE_DAEMON_SOCKET` at it. The SDK's `sse.reference.get_reference_patch` reads it to reach the admin socket. |
| `SSE_AGENT_USER` | `model` | daemon | The agent's user, whose processes the daemon kills when the agent phase ends. |
| `SSE_RUNNER_USER` | `sse-runner` | daemon | The unprivileged user the daemon runs the task's build, PoC and test scripts as, when it runs as root. A dedicated uid with no groups, neither the agent nor root; the tool layer creates it. The daemon refuses to start as root without it. |
| `SSE_RUNNER_DIR` | `/var/lib/ssebench-runner` | daemon | The root of the task runner's scratch copies, reachable only by the runner and root (`0710`). Each check runs in a private copy of the project here. |
| `SSE_DAEMON_TIMEOUT` | `300` | entrypoint | Seconds to wait for the daemon's socket. |
| `SSE_MCP_TIMEOUT` | `300` | entrypoint | Seconds to wait for the MCP server. |
| `SSE_DEBUG` | unset | entrypoint | Any non-empty value turns on debug logs. |
| `SSE_PLUGIN_NAME` | unset | plugins | Set by the entrypoint for a plugin it runs; the plugin's name. |
| `SSE_PLUGIN_HOOK` | unset | plugins | Set by the entrypoint for a plugin it runs; the hook it runs at, such as `after-grading`. |
| `SSE_PLUGIN_SKIP_FILE` | unset | plugins | Set by the entrypoint for a plugin it runs; the path of a file the plugin writes a reason to when it chooses not to run. The entrypoint then records the plugin as `skipped` and logs the reason. |
| `SSE_ORACLE_FUZZ` | unset | oracle plugin | `1` makes the oracle plugin fuzz the patched project after its review; it installs AFL++, so the run needs `--egress open`. |
| `SSE_BENCH_PATH` | `/ssebench` | daemon | Directory with the task's `config.yaml`, scripts and files. |
| `SSE_HTTP_PORT` | `4263` | daemon | The daemon's agent-facing HTTP port. |
| `SSE_DAEMON_WORKERS` | `4` | daemon | Worker threads for each of the daemon's listeners. Tool calls run on separate blocking threads, so a long build does not keep a worker from answering other requests. Without a limit, actix starts one worker per host CPU for every listener. |
| `SSE_REPO_PATH` | `/ssebench-repo` | daemon | Clean clone of the project that grading applies the agent's diff to and builds. |
| `SSE_AGENT_DOCKER` | unset | SDK | `host:port` of the daemon's HTTP listener, used when `SSE_DAEMON_SOCKET` is not set. |
| `MCP_LOG_DIR` | `/tmp/mcp/logs` | MCP server | Where the MCP server writes the full logs of long check results; see [Long logs](/reference/mcp-server#long-logs). |
| `AGENT_DURATION` | `0` | evaluator | The agent's run time in seconds; the entrypoint sets it for the evaluator. |
| `AGENT_EXIT_STATUS` | unset | evaluator | The agent's exit status, 124 when it hit its time limit; the entrypoint sets it for the evaluator, which records it as `agent_exit_code`. |
| `SSE_METRIC_AGENT_TIMEOUT` | unset | evaluator | Set to `true` by the entrypoint for the evaluator when the agent hit its time limit. |
| `CLAUDE` | unset | claude-code agent | Path of the Claude Code executable; the `claude-code` agent image sets it. |
| `OPENCODE_CONFIG_CONTENT` | unset | OpenCode | OpenCode's configuration as JSON; `sse.ai` and the `opencode` agent set it for the OpenCode server they start. |

<!-- end generated -->

### Sockets and ports

| Service | Address |
|---------|---------|
| Daemon, agent-facing Unix socket | `/tmp/sse.sock` in sandbox mode; `/run/ssebench/sse.sock` in sidecar mode. Mode `0666`, so the `model` user can connect. |
| Daemon, admin Unix socket | `/run/ssebench/admin.sock`. Mode `0600`, root-only: grading, the reference patch and phase changes. |
| Daemon, HTTP | port `4263` on all interfaces; the web UI connects to it. Agent-facing, so difficulty-gated like the agent socket. |
| MCP server | `http://localhost:3000/mcp`, streamable HTTP; see [MCP server](/reference/mcp-server) |
| OpenCode server | port `4096` on all interfaces, in sandbox mode when `opencode` is on the `PATH` |

In sidecar mode `/run/ssebench` is a volume the two containers share. It is
owned by root and writable only by root, so the agent can use the sockets in it
but cannot replace them.

The reference patch is served at `GET /reference/patch` on the admin socket at
any time, and on the agent-facing socket and HTTP only after the agent phase
ends (the entrypoint sends `POST /admin/agent_exited` over the admin socket when
the agent exits, which is how the web UI reads it from the host post-run).
Post-agent SDK tooling uses `sse.reference.get_reference_patch()`. The
[integrity model](/concepts/integrity) explains the two kinds of listener.

The LiteLLM proxy is `litellm:4000` on two networks of its Compose project. By
default the task container joins the internal one, `<project>_agents`
(`ssebench_agents` by default), which reaches the proxy but not the internet.
`ssebench run --egress open` puts it on `<project>_default` instead, a normal
bridge; see [Integrity and egress](/deployment/integrity-and-egress).

### Result files

`ssebench run` mounts the run directory, `results/<task>/<model>/<agent>/<run-id>/`
under the working directory, at `SSE_RESULTS` (root-only), and its `archive/`
subdirectory at `SSE_ARCHIVE` (the agent's). Every run has a new directory.
[Results format](/concepts/results) describes every file.

| File | Written by | Contents |
|------|------------|----------|
| `result.json` | evaluator, to the results directory; `ssebench run` adds `config` | The grade: `patch_result` and `runtime_result`, and the run settings |
| `agent.log`, `daemon.log`, `mcp.log`, `evaluator.log`, `opencode.log` | entrypoint | The output of each process; a second run in the same container appends to them |
| `entrypoint.log` | entrypoint | The entrypoint's own log, only for a mode that sets `LogTo` to `LogToFile` |
| `archive/dialog.jsonl` | agent | The agent's session; see [Dialog protocol](/reference/dialog-protocol) |
| `final.patch`, `commits.log` | daemon, when grading starts | The agent's diff and commit messages |
| `scriptrunner-<ms>.log`, `patch-<ms>.log` | daemon | The output of each script the daemon runs, and of each test patch it applies |
| `source.tar.gz` | evaluator | The project source after grading |

`result.json` has this shape:

```json
{
  "patch_result": {
    "status": "failed",
    "build_success": true,
    "pov_passed": 0,
    "pov_total": 1,
    "func_test_success": true,
    "intent_test_success": false,
    "error_msg": "PoC failed: /ssebench/pocs/poc.go",
    "error_log": "..."
  },
  "runtime_result": { "agent_duration": 0, "agent_timeout": false, "evaluator_timeout": false },
  "config": {
    "agent": "dummy",
    "model": "claude-sonnet-4-6",
    "mode": "sandbox",
    "timeout": 3600,
    "difficulty": 2,
    "tool_layer": "sandbox",
    "egress": "restricted",
    "reference_run": false
  }
}
```

The evaluator writes `patch_result` and `runtime_result`; after the container
exits, `ssebench run` adds the run settings as `config`. If the container
leaves `result.json` empty, `ssebench run` records an ungraded run, `status`
`error`, with the error `No result: evaluator did not produce output`. It then
writes the summary, `summary.json` in the run directory: the task metadata
(`task`), the run settings (`config`: `agent`, `model`, `mode`, `timeout`,
`difficulty`, `tool_layer`, `egress` and `reference_run`), `patch_result`,
`runtime_result` and the model `spend` in US dollars. `reference_run` is `true`
when the `reference` agent applied the task's known fix: that grade rates the
task, not a model.

### Container labels

`ssebench run` labels the sandbox container, and in sidecar mode the
environment container:

| Label | Value |
|-------|-------|
| `ssebench.webui` | `true` |
| `ssebench.task-id` | The task ID |
| `ssebench.model` | The model name |
| `ssebench.agent` | The agent name |
| `ssebench.reference-run` | `true` on a [reference run](/reference/cli#reference-runs); absent otherwise |

In sidecar mode, both containers and the two volumes of a run also carry
`ssebench.run`, the run's ID.

The [web UI](/webui/) lists the containers that have `ssebench.webui` and acts
only on those.
