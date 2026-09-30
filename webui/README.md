# SSEBench Web UI

A browser front end for launching SSEBench runs and watching them live: the
agent dialog, the diff, container logs, the evaluation result, an OpenCode
assistant and a terminal inside the run container.

- `src/`: Vite + React client.
- `server/`: Bun + Hono server. It finds, stops and reaches runs through the
  `ssebench runs` commands of the CLI, which use the runner backend, and talks to
  the SSEBench daemon inside each run container and to OpenCode. It never runs
  `docker` itself.
- `pty-proxy/`: Go helper that gives the terminal a real PTY
  ([README](pty-proxy/README.md)).

## How it reaches runs

| The server needs | It runs | Which asks the backend |
|---|---|---|
| The list of runs, and the health of the runner | `ssebench runs list --json` | `list_runs` |
| Finished runs | `ssebench runs results --json` | Nothing: it reads `results/` |
| Logs | `ssebench runs logs --follow ID` | `logs` |
| Stop, remove | `ssebench runs stop ID`, `ssebench runs remove ID` | `stop`, `cleanup` |
| The address of a run's daemon (4263) or OpenCode (4096) | `ssebench runs endpoint --json ID PORT` | `endpoint` |
| A terminal, the assistant's server, a container's variables | `ssebench runs exec [--tty] ID -- COMMAND...` | `exec_argv` |
| A launch | `ssebench run --run-id=ID ...` | the runner |

Each is a process that starts, answers with JSON (or streams lines) and exits,
started with an argument vector and never through a shell. That keeps the server
stateless and lets a test replace the CLI by a script: `server/fakeRunner.ts` is
one. The cost is Python's start-up time, about 0.3 s per call, which the server
hides by sharing the run list for 1.5 s and remembering a run's address for 30 s.
`SSEBENCH_CLI` says how to start the CLI, and `SSEBENCH_BACKEND` which backend it
uses; see [Runner backends](../docs/concepts/runner-backends.md).

A run is named by its run ID (the `--run-id` of `ssebench run`; the launcher uses
a UUID). A finished run whose container is gone is still listed, from its
directory `results/<task>/<model>/<agent>/<run-id>/`, with its dialog, diff, grade,
reference patch and logs, and is read-only.

## Running

Requires [Bun](https://bun.sh/), the `ssebench` CLI (`uv run ssebench` in a
checkout, or `SSEBENCH_CLI`), whatever the CLI needs for its backend (the
`docker` CLI for the default one), and Go to build the terminal helper.

```bash
cd webui
bun install
bun run build:pty   # optional: enables the terminal; `just webui` does this when Go is installed
bun run prod        # build the client, serve everything on http://127.0.0.1:3001
```

For development, `bun run dev` starts the API server and the Vite dev server
(`http://127.0.0.1:5173`), which forwards `/api` to the API server.

Without the terminal helper, or with a backend that cannot run commands in a
run, `/api/health` reports `terminal: false` with a `terminalHint`, and the UI
hides the terminal tabs and shows the hint.

Tests: `bun test` for the server, `go test ./...` in `pty-proxy/`.

### In a container

[`Dockerfile`](Dockerfile) builds an image with the client, the server, the
terminal helper, the `ssebench` CLI and the `docker` CLI. From the repository root:

```bash
docker buildx build -f webui/Dockerfile --build-arg VERSION="$(cat VERSION)" -t ssebench-webui .
docker run --rm --network host -v /var/run/docker.sock:/var/run/docker.sock ssebench-webui
```

The image uses the Docker backend, which needs the Docker socket to list,
inspect and open terminals in the run containers, and the host network to reach
the SSEBench daemon in each of them by its container IP address. It listens on `http://127.0.0.1:3001` as it
does outside a container, and the variables below apply (pass them with
`-e`). Whoever controls the container controls the host's Docker daemon, so
the security notes below apply twice over.

The image watches runs but cannot launch them: it has no SSEBench checkout, so
no models, agents or local tasks to choose from. Start runs with
`ssebench run --keep-container`, or run the web UI from a checkout as above to
launch them from the browser. It reads finished runs from `/app/results`; mount
your `results/` there. Add `-e SSEBENCH_WEBUI_HOSTED=1` for a read-only viewer.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SSEBENCH_WEBUI_HOST` | `127.0.0.1` | Bind address of the API server and of the Vite dev and preview servers. |
| `PORT` | `3001` | API server port; the Vite servers forward `/api` there. |
| `SSEBENCH_WEBUI_TOKEN` | unset | Access token (at least 16 characters). Required when the bind address is not loopback. |
| `SSEBENCH_WEBUI_CORS_ORIGINS` | unset | Comma-separated origins, besides the server's own, allowed to call the API, e.g. `https://bench.example.org`. |
| `SSEBENCH_WEBUI_TERMINAL` | `1` | `0` turns off the container terminal. |
| `SSEBENCH_WEBUI_HOSTED` | `0` | `1` makes the server a read-only viewer: no launch, stop or remove, no terminal, and no command execution by the assistant. |
| `SSEBENCH_CLI` | `uv run ssebench` | How to start the CLI: words separated by white space, run without a shell. The image sets `ssebench`. |
| `SSEBENCH_BACKEND` | `docker` | The runner backend that the CLI uses, for launches and for `ssebench runs`. |
| `SSEBENCH_PATH` | repository root | SSEBench checkout: the CLI runs here, so `results/` is here, and `models/` and `agents/` are read from here. |
| `SSEBENCH_LOCAL_TASKS` | `$SSEBENCH_PATH/datasets/pilot` | Local dataset offered in the launcher. |
| `SSEBENCH_CATALOG` | `$SSEBENCH_PATH/datasets/pilot/manifest.json` | Task catalog offered in the launcher's Catalog tab and passed to `ssebench run --catalog`: the path or URL of a `manifest.json`, a dataset directory, or the base URL of a catalog service. `SSEBENCH_CATALOG_URL`, its former name, still works for this release but is deprecated. |
| `PTY_ENABLE_CLEANUP`, `PTY_CLEANUP_INTERVAL`, `PTY_ORPHAN_THRESHOLD` | `true`, `30000`, `300000` | Cleanup of terminal processes whose browser went away (milliseconds). |

The bind address is read from `SSEBENCH_WEBUI_HOST` rather than `HOST`
because zsh sets `HOST` to the machine's host name, which would expose the
server without anyone asking for it.

## Security

Whoever can use the web UI can launch runs, stop and remove SSEBench
containers, read their logs and ground-truth patches, and, through the
terminal, run commands inside them. Treat access to it like access to those
containers.

**Loopback by default.** The servers listen on `127.0.0.1` unless
`SSEBENCH_WEBUI_HOST` says otherwise. Without a token the API also rejects
requests whose `Host` header is not a loopback name, so a web page cannot
reach it by pointing its own DNS name at `127.0.0.1`. To use the UI from
another machine, prefer an SSH tunnel:

```bash
ssh -L 3001:127.0.0.1:3001 user@server
```

**Token.** To listen on any other address, set a token:

```bash
SSEBENCH_WEBUI_HOST=0.0.0.0 SSEBENCH_WEBUI_TOKEN="$(openssl rand -hex 32)" bun run start
```

The server refuses to start on a non-loopback address without one. With a
token set, every `/api` route, WebSocket and terminal requires it:
`Authorization: Bearer <token>` for HTTP, and for WebSockets (where browsers
cannot set headers) the subprotocol `ssebench.token.<base64url(token)>`
offered next to `ssebench`. The browser asks for the token once and keeps it
in `sessionStorage` for that tab. The token travels in clear text over plain
HTTP, so put a TLS-terminating proxy in front when the network is not
trusted.

**Origins.** The API serves its own origin. Requests and WebSocket
handshakes from any other origin are refused with 403 unless that origin is
listed in `SSEBENCH_WEBUI_CORS_ORIGINS`.

**Runs.** Run operations accept only run IDs (1 to 64 letters, digits, `.`,
`_` and `-`) and act only on runs labelled `ssebench.webui`. The CLI and the
terminal helper are started with argument vectors, never through a shell, and
launch parameters must name a model, agent and task the server lists. Finished
runs are read from `results/` as plain files; a link in the run directory is
not followed, since the agent can write to `archive/`.

**Terminal.** The terminal WebSocket (`/api/pty/<id>`) opens a shell in the
run container as the image's default user, and `/api/pty-debug/<id>` runs
OpenCode's terminal UI there. Set `SSEBENCH_WEBUI_TERMINAL=0` to refuse both;
the UI then hides the terminal tabs.

**Hosted mode.** `SSEBENCH_WEBUI_HOSTED=1` is for a server that shows runs to
people who must not change or run anything. Every request other than a
`GET`, `HEAD` or `OPTIONS` is refused with 403 (launch, cancel, stop, remove),
so are the terminal routes, every route of the AI assistant, which can run
commands in the container, and `/api/launch/doctor`, and the server never starts
the assistant's OpenCode server. Runs, finished runs, dialogs, diffs, logs and
grades stay readable. `/api/health` reports `hosted: true`. It limits what the
server does, not who may ask: set a token too.

**Assistant through the proxy.** For a run that has a model, the assistant uses
that model through the run's LiteLLM proxy instead: the server makes a key for
it with `LITELLM_MASTER_KEY` (environment, or `.env` in `SSEBENCH_PATH`) and a
budget of 5 dollars, and starts a second OpenCode server in the container, on
port 4098, with that key in its environment. It works on the restricted network.
The provider key described next is used only when there is no such model.

**Provider API key.** The API key entered under Settings for the AI
assistant is stored unencrypted in the browser's `localStorage`, where any
script running on the web UI's origin can read it. When an assistant session
starts, the browser sends the key to the web UI server, which pushes it into
the OpenCode server inside the run container; OpenCode keeps it there after
the session ends. Anyone who can open a shell in that container can read it.
Use a key you can revoke, clear it in Settings when you are done, and remove
containers you used the assistant in.
