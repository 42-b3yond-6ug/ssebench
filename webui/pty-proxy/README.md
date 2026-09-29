# PTY Proxy

A small Go program that gives the webui terminal a real pseudo-terminal inside
a Docker container. The Bun backend starts one proxy process per terminal
session.

## Why?

Bun has no native PTY support (no equivalent of node-pty), and piping
`docker exec -it` through a wrapper does not give proper terminal control,
especially resize. The proxy:

- creates a **real PTY** with `github.com/creack/pty`;
- handles **terminal resize** (`TIOCSWINSZ`);
- talks to the backend over **stdin/stdout** with JSON lines;
- exits when the container process exits or it receives `SIGINT`/`SIGTERM`.

## Architecture

```
Frontend (xterm.js)
    ↕ WebSocket (ws://<host>:3001/api/pty/:containerId)
Bun backend (server/pty.ts)
    ↕ stdin/stdout, JSON lines
pty-proxy (this program)
    ↕ PTY running `docker exec -it`
Docker container shell
```

## Building

The binary is not checked in. Build it before using the terminal:

```bash
# from webui/
bun run build:pty

# or directly
cd pty-proxy
CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X main.version=$(cat ../../VERSION)" -o pty-proxy .
```

`pty-proxy --version` prints the SSEBench version it was built from.

The backend looks for the binary at `webui/pty-proxy/pty-proxy`. If it is
missing, terminal sessions report an error instead of starting.

## Usage

```bash
pty-proxy [--workdir WORKDIR] <container-id> [command [arg...]]
```

- `<container-id>`: hexadecimal container ID (12 to 64 characters).
- `command [arg...]`: what to run in the container (default `bash`). The
  words are passed to `docker exec` as separate arguments; nothing is parsed
  by a shell.
- `--workdir`: working directory inside the container (`docker exec -w`).

There is no standalone server mode; the program is meant to be run by the
backend.

## Protocol

stdin (JSON lines from the backend):

```json
{"type": "input", "data": "ls\n"}
{"type": "resize", "cols": 80, "rows": 24}
```

stdout (JSON lines to the backend):

```json
{"type": "output", "data": "hello world"}
{"type": "error", "message": "Container not found"}
{"type": "exit", "code": 0}
```

Logs go to stderr with a `[PTY-PROXY]` prefix.

## Dependencies

- `github.com/creack/pty`, the only dependency.
- The `docker` CLI on `PATH` at run time.
