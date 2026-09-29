---
outline: deep
---

# Extension points

Third parties can extend SSEBench from their own package, without forking
it:

- a **tool layer** changes the runtime image that the agent runs in, and is
  selected with `ssebench run --tool-layer NAME`;
- a **command** adds a subcommand, `ssebench NAME`;
- a **container mode** changes how the entrypoint orchestrates the task
  container, and is selected with `entrypoint --mode NAME`.

A Python package registers tool layers and commands as
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
tool layer and the command shown below. The tests in
`bench/tests/test_extensions.py` install it and use both.

| Group | Name selects | Object |
|-------|--------------|--------|
| `ssebench.tool_layers` | `ssebench run --tool-layer NAME` | a subclass of `ToolLayer` |
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
- `ToolLayerContext` has three fields:
  - `task_name`: the task ID, for example `gjson-196-bf4efcb`;
  - `source_dir`: the absolute path of the project source in the case image;
  - `build_root`: the SSEBench home, which holds `images/`, `runtime/` and
    `sdk/` and is the build context of the built-in layers.
- `docker_image(base)` gets the name of the case image, builds the tool image
  on top of it and returns the tool image's name. The agent image is then built
  from that image. The tool image must meet the
  [image contract](#image-contract).
- Build on `SandboxToolLayer` to keep the standard runtime. Use `REGISTRY`,
  the image prefix that `SSEBENCH_REGISTRY` sets, to name images like the
  built-in ones do.

This layer adds one Docker layer on top of the standard runtime:

```python
import subprocess
from typing import override

from ssebench.extensions import REGISTRY, SandboxToolLayer, ToolLayer

DOCKERFILE = """\
FROM runtime
LABEL org.example.tool-layer="example"
"""


class ExampleToolLayer(ToolLayer):
    @override
    def docker_image(self, base: str | None) -> str:
        runtime = SandboxToolLayer(self.context).docker_image(base)
        image = f"{REGISTRY}/tool-example/{self.context.task_name.lower()}"
        subprocess.run(
            ["docker", "buildx", "build",
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
| `Configurer` | Optional interface with `Configure(cfg *Config)`, called before the `TIMEOUT`, `SSE_DAEMON_TIMEOUT` and `SSE_MCP_TIMEOUT` overrides; the sidecar mode uses it to move the sockets and paths |

Before `Run`, the entrypoint installs the SIGINT and SIGTERM handler, makes
`SSE_ARCHIVE` world-writable and creates the log files. After `Run` returns,
it stops every service the mode started and exits with the returned status.
Inside `Run`, the mode uses the `*Runtime`:

| Method | Description |
|--------|-------------|
| `Config() Config` | Paths, sockets and timeouts of this run |
| `AgentCommand() []string` | The agent command, from the arguments after `--` |
| `Logger() *slog.Logger` | The entrypoint's logger |
| `LogPath(name string) string` | `<SSE_ARCHIVE>/<name>.log` |
| `StartDaemon() error` | Starts the daemon with its agent-facing and admin sockets |
| `WaitForDaemon() error` | Waits for a daemon in another container, as the sidecar mode does |
| `StartMCPServer() error` | Starts the MCP server and waits until it answers |
| `StartOpenCodeServer()` | Starts OpenCode on port 4096 if it is installed |
| `StartService(name string, argv []string, dir string, env []string) error` | Starts another background process, logged to `LogPath(name)` |
| `RunAgent() (AgentResult, error)` | Runs the agent as `model` with its time limit, then ends the agent phase |
| `EndAgentPhase()` | Ends the agent phase; only the first call has an effect |
| `Evaluate(result AgentResult)` | Ends the agent phase, then grades through the admin socket and writes `/sse_result` |
| `KeepAlive()` | Blocks while `SSE_KEEP_ALIVE=1` keeps the container for the web UI |

`AgentResult` has the agent's `ExitStatus` (124 when it was killed at its time
limit), its `Duration` and `TimedOut`.

The daemon serves the reference patch on its agent-facing socket and HTTP
port only after the agent phase ends. `RunAgent` ends it once the agent has
exited, and `Evaluate` ends it before grading at the latest. A mode whose
agent does not run through `RunAgent`, for example because it runs
elsewhere, calls `EndAgentPhase` when the agent is done, and never before.

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
- write the grade to `/sse_result` before it exits (the evaluator does this);
- keep the paths below. An agent Dockerfile builds on the tool image with
  `FROM ssebench-agent`; `ssebench run` passes the tool image as the
  `ssebench-agent` build context.

| Path | Contents |
|------|----------|
| `/usr/local/bin/entrypoint` | The container entrypoint (`runtime/entrypoint`) |
| `/ssebench/ssebench-daemon` | The daemon (`sdk/daemon`) |
| `/ssebench/mcp` | The MCP server (`runtime/mcp`) and its virtual environment |
| `/evaluator` | The evaluator (`runtime/evaluator`) and its virtual environment |
| `/ssebench` | The task's scripts and files from the case image; root only |
| `/ssebench-repo` | The original project source; root only |
| `source_dir` from the task's `config.yaml` | The project source, owned by `model`, with its git history replaced by one commit |
| `/sse_result` | The evaluator's result, bind-mounted from the host |
| `/tmp/sse-archive` | The run's results directory (`SSE_ARCHIVE`), bind-mounted from the host |
| `/reference/patch.diff` | The task's reference patch, bind-mounted read-only for the `reference` agent and no other; see [Reference runs](/reference/cli#reference-runs) |

In the sidecar agent image the MCP server is in `/mcp`, and the task files
come from the environment container through a shared volume.

### Environment variables

`ssebench run` sets these in the task container. In sidecar mode, the agent
container gets them all except `SSE_KEEP_ALIVE`, and the environment container
gets `SSE_ARCHIVE`, `SSE_DAEMON_SOCKET` and `SSE_KEEP_ALIVE`.

| Variable | Value |
|----------|-------|
| `SSE_API_KEY` | The run's LiteLLM key, which can use only the selected model |
| `SSE_BASE_URL` | The LiteLLM proxy, `http://litellm:4000` |
| `SSE_MODEL_NAME` | The selected model, as named in `models/*.yaml` |
| `SSE_ARCHIVE` | The results directory in the container, `/tmp/sse-archive` |
| `SSE_DIFFICULTY` | The [difficulty level](/concepts/difficulty-levels), from 0 to 4 |
| `TIMEOUT` | The agent's time limit in seconds (`--timeout`); the evaluator uses the same limit |
| `SSE_KEEP_ALIVE` | `1` keeps the container running after the run (`--keep-container`), otherwise `0` |
| `SSE_DAEMON_SOCKET` | Sidecar mode only: the daemon's Unix socket, `/tmp/sse-archive/please-work.sock` |

A [reference run](/reference/cli#reference-runs) uses no model:
`SSE_MODEL_NAME` is `none`, and `SSE_API_KEY` and `SSE_BASE_URL` are empty.

The components in the container read these, with these defaults:

| Variable | Read by | Default | Description |
|----------|---------|---------|-------------|
| `SSE_ARCHIVE` | entrypoint, daemon, evaluator, agents | required by the entrypoint; `/tmp/sse-archive` in the daemon and agents | Where logs, `dialog.jsonl` and the final patch go |
| `SSE_DAEMON_SOCKET` | entrypoint (sidecar mode), daemon, SDK | `/tmp/sse.sock` in sandbox mode | The daemon's agent-facing Unix socket (mode `0666`). The entrypoint sets it for every process it starts; without it, the daemon serves HTTP only |
| `SSE_ADMIN_SOCKET` | entrypoint, daemon, evaluator | `/run/ssebench/admin.sock` in sandbox mode | The daemon's privileged Unix socket (mode `0600`, root-only). Grading, the reference patch and phase changes go here; the agent cannot reach it |
| `SSE_HTTP_PORT` | daemon | `4263` | The daemon's agent-facing HTTP port |
| `SSE_BENCH_PATH` | daemon | `/ssebench` | The task's scripts and files |
| `SSE_REPO_PATH` | daemon | `/ssebench-repo` | The original project source |
| `SSE_AGENT_DOCKER` | SDK | unset | `host:port` of the daemon's HTTP API, used when `SSE_DAEMON_SOCKET` is not set |
| `SSE_DIFFICULTY` | MCP server, daemon | `2` | Which checks `test_patch` runs. The daemon reads it too and rejects withheld `bencher` actions (403) on the agent-facing listeners |
| `MCP_LOG_DIR` | MCP server | `/tmp/mcp/logs` | Where the full logs of long check results go |
| `TIMEOUT` | entrypoint, evaluator | `14400` (entrypoint), `1800` (evaluator) | Time limits in seconds |
| `SSE_DAEMON_TIMEOUT` | entrypoint | `300` | Seconds to wait for the daemon socket |
| `SSE_MCP_TIMEOUT` | entrypoint | `300` | Seconds to wait for the MCP server |
| `SSE_KEEP_ALIVE` | entrypoint | `0` | `1` keeps a sandbox container running after grading |
| `SSE_DEBUG` | entrypoint | unset | Any non-empty value turns on debug logs |

The entrypoint passes two more variables to the evaluator: `AGENT_DURATION`,
the agent's run time in seconds, and `SSE_METRIC_AGENT_TIMEOUT=true` when the
agent hit its time limit.

### Sockets and ports

| Service | Address |
|---------|---------|
| Daemon, agent-facing Unix socket | `/tmp/sse.sock` in sandbox mode; `/tmp/sse-archive/please-work.sock` in sidecar mode, shared through the results directory. Mode `0666`, so the `model` user can connect. |
| Daemon, admin Unix socket | `/run/ssebench/admin.sock` in sandbox mode; `/tmp/sse-archive/admin.sock` in sidecar mode. Mode `0600`, root-only: grading, the reference patch and phase changes. |
| Daemon, HTTP | port `4263` on all interfaces; the web UI connects to it. Agent-facing, so difficulty-gated like the agent socket. |
| MCP server | `http://localhost:3000/mcp`, streamable HTTP; see [MCP server](/reference/mcp-server) |
| OpenCode server | port `4096` on all interfaces, in sandbox mode when `opencode` is on the `PATH` |

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

`ssebench run` mounts `results/<task>/<model>/<agent>/`, under the working
directory, at `SSE_ARCHIVE`. The directory is emptied before each run.
[Results format](/concepts/results) describes every file.

| File | Written by | Contents |
|------|------------|----------|
| `result.json` | evaluator, through `/sse_result`; `ssebench run` adds `config` | The grade: `patch_result` and `runtime_result`, and the run settings |
| `agent.log`, `daemon.log`, `mcp.log`, `evaluator.log`, `opencode.log` | entrypoint | The output of each process |
| `dialog.jsonl` | agent | The agent's session; see [Dialog protocol](/reference/dialog-protocol) |
| `final.patch`, `commits.log` | daemon, when grading starts | The agent's diff and commit messages |
| `scriptrunner-<ms>.log`, `patch-<ms>.log` | daemon | The output of each script the daemon runs, and of each test patch it applies |
| `source.tar.gz` | evaluator | The project source after grading |

`result.json` has this shape:

```json
{
  "patch_result": {
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
leaves `result.json` empty, `ssebench run` records a failed run with the error
`No result: evaluator did not produce output`. It then writes the summary,
`results/<task>-<agent>-<model>.json`: the task metadata (`task`), the run
settings (`config`: `agent`, `model`, `mode`, `timeout`, `difficulty`,
`tool_layer`, `egress` and `reference_run`), `patch_result`, `runtime_result`
and the model `spend` in US dollars. `reference_run` is `true` when the
`reference` agent applied the task's known fix: that grade rates the task, not
a model.

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

The [web UI](/webui/) lists the containers that have `ssebench.webui` and acts
only on those.
