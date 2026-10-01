---
outline: deep
---

# Web UI

The web UI launches runs and lets you watch them live: the agent's session, the
diff of its changes, a terminal into the task container, the logs, and the
evaluation result. It also reads finished runs from `results/`, after their
containers are gone, and it works with any [runner backend](/concepts/runner-backends).

## Start the web UI

You need [Bun](https://bun.sh/). From the repository root:

```sh
just webui
```

This is the same as `cd webui && bun install && bun run prod`: it installs the
dependencies, builds the front end and starts the server. Then open
`http://localhost:3001`. Set `PORT` to use a different port.

The recipe also builds the terminal helper, `pty-proxy`, when Go is installed.
Without it the web UI starts with the terminal off, and says how to build it; run
`bun run build:pty` in `webui/` once, which needs Go. See
[Watching a run](/webui/run-view#terminal).

::: warning
The web UI can start runs and open shells in task containers on its host. Don't
expose it to a network you don't trust. See [Security model](/webui/security).
:::

To use the web UI on a remote machine, forward its port over SSH instead of
opening it to the network:

```sh
ssh -L 3001:localhost:3001 user@your-server
```

and open `http://localhost:3001` on your own machine.

### In a container

The web UI is also published as an image,
`ghcr.io/42-b3yond-6ug/ssebench/webui:<version>`, for `linux/amd64` and
`linux/arm64`. Run it on the host network with the Docker socket mounted:

```sh
docker run --rm --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/42-b3yond-6ug/ssebench/webui:<version>
```

It needs the socket because the image uses the Docker backend, which manages
the run containers through it, and the host network to reach the SSEBench daemon
in each of them by its container IP address. It listens on
`http://127.0.0.1:3001` like the web UI started from a checkout, and takes the
same environment variables (see `webui/README.md`). Access to the socket is root
access to the host, so run it only on a machine you control. To show runs
read-only, add `-e SSEBENCH_WEBUI_HOSTED=1`; see [Hosted mode](#hosted-mode).

On Docker Desktop, `--network host` is the virtual machine's network and works
only with **Enable host networking** turned on (4.34 or later); it is untested.
See [macOS and Docker Desktop](/deployment/host#macos-and-docker-desktop).

`just demo` starts this image, with the catalog and the LiteLLM proxy, and opens
a finished run in it; see [Run the demo](/getting-started/try#run-the-demo).

The image carries the `ssebench` CLI, which the server uses to find and reach
runs (`SSEBENCH_CLI=ssebench`), and the `docker` and `kubectl` CLIs. It has no
SSEBench checkout, so its launch wizard offers the models and agents that were
copied into the image and the tasks of `SSEBENCH_CATALOG`, but no local tasks. On the
Docker backend, start runs with `ssebench run --keep-container`, or start the web UI
from a checkout to launch runs from the browser. Finished runs are read from `results/` in the image's
`/app`; mount your results directory there with `-v "$PWD/results:/app/results"`
to see them. To build the image yourself, run
`docker buildx build -f webui/Dockerfile .` from the repository root.

## What it does

- **Launch wizard:** pick a task, an agent, a model and an execution mode, then
  follow the launch output. See [Launching runs](/webui/launching-runs).
- **Runs:** the web UI lists the task containers that SSEBench started, and the
  finished runs in `results/` whose containers are gone. Runs it launches keep
  their container after they finish, so you can still inspect them.
- **Run view:** the agent's dialog and tool calls, the diff of its changes, a
  terminal into the container, the component logs, and the evaluation result.
  A finished run shows all of it except the terminal and the assistant, from its
  run directory. See [Watching a run](/webui/run-view).

The dialog view reads the `dialog.jsonl` file that each agent writes; see the
[dialog protocol](/reference/dialog-protocol).

To inspect a run started from the command line, pass `--keep-container` to
`ssebench run`.

## Backends

The web UI never calls `docker` or `kubectl` itself. To list, stop, remove and
reach runs it runs [`ssebench runs`](/reference/cli#ssebench-runs), which asks the
[runner backend](/concepts/runner-backends) for them, so one build of the web UI
serves any backend:

| The web UI needs | Which the CLI gets from |
|---|---|
| The runs, their state and logs, stopping and removing | `list_runs`, `logs`, `stop` and `cleanup` of the backend |
| The address of a run's daemon (port 4263) and OpenCode server (port 4096) | `endpoint` of the backend |
| A terminal, and the assistant's server, in a run | `exec_argv` of the backend, if it has one |
| Finished runs | The `summary.json` files in `results/`; no backend |

The backend is the one that `SSEBENCH_BACKEND` names (Docker by default), as for
`ssebench run`. `SSEBENCH_CLI` says how the server starts the CLI, `uv run
ssebench` in `SSEBENCH_PATH` by default. A backend whose runs cannot run commands
has no terminal and no assistant, and `/api/health` says so with `terminal:
false` and `assistant: false`. The server asks the CLI a fresh question about
once a second at most, and keeps the address of a run's daemon for 30 seconds.

A backend that has to be given prebuilt images needs them for a launch too:
start the server with `SSEBENCH_PREBUILT=1`, and the launched `ssebench run` uses
`--prebuilt`. The image also carries the Python client and `kubectl` of the
[Kubernetes backend](/deployment/kubernetes), and the
[Helm chart](/deployment/kubernetes#install-with-helm) runs it there with
`SSEBENCH_BACKEND=kubernetes`, in [hosted mode](#hosted-mode) unless you turn it off.

## Hosted mode

`SSEBENCH_WEBUI_HOSTED=1` makes the server a read-only viewer, for a showcase or
a server that many people reach. It shows runs, live and finished, and changes
nothing:

- launching, stopping and removing are refused with `403`, and the UI hides
  their buttons;
- there is no terminal, whatever `SSEBENCH_WEBUI_TERMINAL` says;
- the AI assistant is off, since it can run commands in the container: its routes
  answer `403`, and the server never starts an OpenCode server;
- `/api/launch/doctor`, which reports on the host, answers `403`.

`/api/health` reports `hosted: true`. Set a [token](/webui/security#token) as
well when the server is reachable by others; hosted mode limits what the server
does, not who may ask. See [Security model](/webui/security#hosted-mode).
