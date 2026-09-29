---
outline: deep
---

# Sandbox and sidecar

`ssebench run --mode` chooses how a run lays out the agent and the project in
containers. Both modes run the same task, the same daemon and the same
grading, and write [results](/concepts/results) in the same format; the run
summary records the mode in `config.mode`. They differ in where the agent runs
and what it has at hand.

|  | Sandbox (default) | Sidecar (experimental) |
|---|---|---|
| Containers | One: the task container | Two: an agent container and a task container |
| The agent's filesystem | The case image: the project and its toolchain | The runtime image and the agent; the project's source tree comes from the task container through a shared volume |
| Building and testing | The agent's own shell, or the daemon | The daemon only, through `test_patch` or the SDK |
| Daemon | In the task container | In the task container |
| MCP server and evaluator | In the task container | In the agent container |
| Images | `tool/<task>`, and the agent on top, `agent-<name>/<task>` | `tool-sidecar/<task>` for the task; `runtime` and the agent on top, `agent-<name>/sidecar`, shared by every task |
| `--tool-layer` | Yes | No; sidecar mode has its own two layers |

Image names are under `SSEBENCH_REGISTRY` and tagged with the SSEBench version;
see [Image layers](/concepts/image-layers).

## Sandbox mode

```
+-- task container ----------------------------------------+
|  entrypoint (root)                                       |
|    ssebench-daemon, MCP server, evaluator (root)         |
|    agent (model)  <-- edits, builds, tests -->  project  |
+----------------------------------------------------------+
```

The agent image is built on the task's tool image, so the agent runs next to
the project, with the task's toolchain on its `PATH`. The entrypoint starts the
daemon and the MCP server, runs the agent as the unprivileged user `model`,
and then runs the evaluator. See
[What happens during a run](/concepts/architecture#what-happens-during-a-run).

Use it unless you have a reason not to: every bundled agent is built for it.

## Sidecar mode

```
+-- agent container ------------+          +-- task container ----------------+
|  entrypoint (root)            |          |  ssebench-daemon (root)          |
|  MCP server, evaluator (root) |          |  project toolchain               |
|  agent (model)                |          |  /ssebench, /ssebench-repo       |
+-------------------------------+          +----------------------------------+
     shared:  the project's source tree     (volume, owned by model)
              /run/ssebench, both sockets   (volume, root-owned)
              /tmp/sse-archive              (results/ on the host)
```

The agent image is built once on the task-independent runtime image
(`images/sidecar-agent`), so one agent image serves every task. The task image
is the case image with the daemon added (`images/sidecar-case`); it has no
agent, MCP server or evaluator.

A sidecar run:

1. creates two volumes, one for the project's source tree and one for the
   daemon's sockets;
2. starts the task container. The empty source volume is filled with the
   project from the image, and the daemon binds its sockets in
   `/run/ssebench`;
3. starts the agent container. Its entrypoint waits for the daemon's socket,
   starts the MCP server, runs the agent as `model`, and then runs the
   evaluator, which grades over the daemon's admin socket. The build, the
   proofs of concept and the tests run in the task container, on a clean copy
   of the project with the agent's changes applied, as in sandbox mode;
4. removes the task container and both volumes. With `--keep-container`, it
   keeps the task container, the volumes and the agent container.

Both containers join the same network, chosen by `--egress`, and get the same
`--difficulty`. Both containers and the volumes carry the label
`ssebench.run=<run id>`; the CLI logs the run ID when it starts the task
container. Remove a kept run with
`docker rm -f $(docker ps -aq --filter label=ssebench.run=<run id>)` and then
`docker volume rm $(docker volume ls -q --filter label=ssebench.run=<run id>)`.

Use it when the agent cannot run in the task's image, for example because its
dependencies conflict with the project's toolchain, or when you want to build
an agent image once for a whole dataset.

### Limits

Sidecar mode is experimental. It passes the same end-to-end and
[integrity](#security-properties) checks as sandbox mode, but:

- The agent container has no toolchain for the project. An agent that builds
  or runs tests with its own shell cannot do so there; it has to use the MCP
  server's `test_patch` tool, or the SDK's `bash` and `bencher` tools, which
  run in the task container; see
  [Add an agent](/guides/add-an-agent#check-the-work).
- The bundled `opencode` agent does not work: it drives an OpenCode server that
  only the sandbox image has.
- The web UI finds a run by its task container, so its terminal opens in the
  task container, not where the agent runs.

## Security properties

The [integrity model](/concepts/integrity) describes these protections, and
their limits, in full. In both modes:

- The agent runs as `model` (uid 1000), created fresh with no supplementary
  groups. The entrypoint, the daemon, the MCP server and the evaluator run as
  root. The task's build, PoC and test scripts run as `sse-runner`, a third
  uid with no groups, in a scratch copy of the project.
- The task's files in `/ssebench` (the reference patch, the hidden tests, the
  proofs of concept and the scripts) and the original source in
  `/ssebench-repo` are readable only by root; the runner gets only a copy of
  what a check needs.
- The grade and the logs go to a root-only results directory; the agent's own
  files (its dialog) go to a separate archive directory.
- The project's git history is replaced by a single commit.
- The daemon's agent-facing Unix socket (mode 0666) and HTTP listener (port
  4263) refuse the checks the [difficulty level](/concepts/difficulty-levels)
  withholds, and every tool once the agent phase ends. Grading and the
  reference patch go through a separate admin socket, mode 0600 and root-only;
  the reference patch is never served on the agent-facing listeners.
- With the default `--egress restricted`, the run's containers are on an
  internal network: they reach the LiteLLM proxy but not the internet.

In sidecar mode, also:

- `/ssebench` and `/ssebench-repo` never reach the agent container; they exist
  only in the task container. The agent acts there only through the daemon,
  whose `bash` tool runs commands as `model`.
- Both daemon sockets are in `/run/ssebench`, on a volume that is owned by root
  and not writable by anyone else. The agent can connect to the agent-facing
  socket, but cannot connect to the admin socket, or move or replace either
  socket. The results directory cannot hold them: it is root-only, so the agent
  cannot put a server of its own in the daemon's place.
- The results directory is mounted root-only in both containers; only the
  agent's archive directory is writable by the agent.
- The task container runs with the run's difficulty level and on the run's
  network, so the difficulty gate and the egress policy also apply to what the
  agent runs through the daemon.

What the agent shares with the task container is the project's source tree,
which it is meant to edit, and its archive directory, which is writable by the
agent in both modes.

`tests/integrity/test_bypass.py` checks these properties in both modes: it holds
a run in its agent phase and runs a fake agent as `model` that tries to read
the protected files, directly and through the daemon's `bash` tool, reach the
admin socket, move the sockets, run withheld checks, read the reference patch
and reach the internet, and that `model` has no supplementary groups. A second
test commits a malicious build/test hook and confirms it runs as `sse-runner`,
reaches neither the hidden material nor the grade in `test_patch` or grading,
and leaves no process behind; another confirms a second run on the network
cannot fetch the first's reference patch. `tests/e2e/smoke.sh sidecar` runs the
`dummy` agent end to end in sidecar mode and checks its grade.
