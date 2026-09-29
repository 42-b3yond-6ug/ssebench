# SSEBench Web UI

A browser front end for launching SSEBench runs and watching them live: the
agent dialog, the diff, container logs, the evaluation result, an OpenCode
assistant and a terminal inside the run container.

- `src/`: Vite + React client.
- `server/`: Bun + Hono server. It talks to the Docker CLI, the SSEBench
  daemon inside each run container, and OpenCode.
- `pty-proxy/`: Go helper that gives the terminal a real PTY
  ([README](pty-proxy/README.md)).

## Running

Requires [Bun](https://bun.sh/), the `docker` CLI, and Go to build the
terminal helper.

```bash
cd webui
bun install
bun run build:pty   # optional: enables the terminal
bun run prod        # build the client, serve everything on http://127.0.0.1:3001
```

For development, `bun run dev` starts the API server and the Vite dev server
(`http://127.0.0.1:5173`), which forwards `/api` to the API server.

Tests: `bun test` for the server, `go test ./...` in `pty-proxy/`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SSEBENCH_WEBUI_HOST` | `127.0.0.1` | Bind address of the API server and of the Vite dev and preview servers. |
| `PORT` | `3001` | API server port; the Vite servers forward `/api` there. |
| `SSEBENCH_WEBUI_TOKEN` | unset | Access token (at least 16 characters). Required when the bind address is not loopback. |
| `SSEBENCH_WEBUI_CORS_ORIGINS` | unset | Comma-separated origins, besides the server's own, allowed to call the API, e.g. `https://bench.example.org`. |
| `SSEBENCH_WEBUI_TERMINAL` | `1` | `0` turns off the container terminal. |
| `SSEBENCH_PATH` | repository root | SSEBench checkout: `uv run ssebench` runs here, and `models/` and `agents/` are read from here. |
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

**Containers.** Container operations accept only hexadecimal container IDs
and act only on containers labelled `ssebench.webui`. Docker, `uv` and the
terminal helper are started with argument vectors, never through a shell,
and launch parameters must name a model, agent and task the server lists.

**Terminal.** The terminal WebSocket (`/api/pty/<id>`) opens a shell in the
run container as the image's default user, and `/api/pty-debug/<id>` runs
OpenCode's terminal UI there. Set `SSEBENCH_WEBUI_TERMINAL=0` to refuse both;
the UI then hides the terminal tabs.

**Provider API key.** The API key entered under Settings for the AI
assistant is stored unencrypted in the browser's `localStorage`, where any
script running on the web UI's origin can read it. When an assistant session
starts, the browser sends the key to the web UI server, which pushes it into
the OpenCode server inside the run container; OpenCode keeps it there after
the session ends. Anyone who can open a shell in that container can read it.
Use a key you can revoke, clear it in Settings when you are done, and remove
containers you used the assistant in.
