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
