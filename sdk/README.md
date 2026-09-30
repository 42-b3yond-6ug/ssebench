# sdk

The API that code inside a task container uses to build, test and inspect the
project under evaluation.

| Directory | Language | What it is |
|---|---|---|
| [`daemon/`](daemon/) | Rust | `ssebench-daemon`: serves the build, PoC and test actions, the diff of the agent's changes and the grade over a Unix socket and HTTP. [`openapi.yaml`](daemon/openapi.yaml) describes its routes. |
| [`python/`](python/) | Python | `ssebench-sdk`, imported as `sse`: the client that agent wrappers, the MCP server and the evaluator use. |
| [`tests/integration/`](tests/integration/) | Python, Docker | Runs the SDK against a real daemon in a container. |

Test the daemon with `just test rust` and the SDK with `just test python`.
The routes and their fields are checked against `daemon/openapi.yaml`
(`cargo test --test openapi`), and the reference pages are generated from it and
from the SDK's docstrings: after you change either, run `just docs-gen`.

- [Daemon HTTP API](../docs/reference/daemon-api.md)
- [Python SDK](../docs/reference/python-sdk.md)
- [Integrity model](../docs/concepts/integrity.md): what the daemon keeps away
  from the agent
