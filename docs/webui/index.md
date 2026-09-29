---
outline: deep
---

# Web UI

The web UI launches runs and lets you watch them live: the agent's session, the
diff of its changes, a terminal into the task container, the logs, and the
evaluation result.

## Start the web UI

You need [Bun](https://bun.sh/). From the repository root:

```sh
just webui
```

This is the same as `cd webui && bun install && bun run prod`: it installs the
dependencies, builds the front end and starts the server. Then open
`http://localhost:3001`. Set `PORT` to use a different port.

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

It needs the socket to manage the run containers, and the host network to
reach the SSEBench daemon in each of them by its container IP address. It
listens on `http://127.0.0.1:3001` like the web UI started from a checkout,
and takes the same environment variables (see `webui/README.md`). Access to
the socket is root access to the host, so run it only on a machine you
control.

The image shows runs but cannot launch them, since it has no SSEBench checkout
and no `uv`: start runs with `ssebench run --keep-container`, or start the web
UI from a checkout to launch runs from the browser. To build the image
yourself, run `docker buildx build -f webui/Dockerfile .` from the repository
root.

## What it does

- **Launch wizard:** pick a task, an agent, a model and an execution mode, then
  follow the launch output. See [Launching runs](/webui/launching-runs).
- **Runs:** the web UI lists the task containers that SSEBench started. Runs it
  launches keep their container after they finish, so you can still inspect
  them.
- **Run view:** the agent's dialog and tool calls, the diff of its changes, a
  terminal into the container, the component logs, and the evaluation result.
  See [Watching a run](/webui/run-view).

The dialog view reads the `dialog.jsonl` file that each agent writes; see the
[dialog protocol](/reference/dialog-protocol).

To inspect a run started from the command line, pass `--keep-container` to
`ssebench run`.
