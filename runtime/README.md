# runtime

What runs inside a task container besides the agent, and the plugins that hook
into a run.

| Directory | Language | What it is |
|---|---|---|
| [`entrypoint/`](entrypoint/) | Go | The container entrypoint. It starts the daemon, then the MCP server, then the agent as the unprivileged user `model`, then the evaluator. `pkg/entrypoint` is also a library for adding container modes; `examples/hello-mode` shows how. |
| [`evaluator/`](evaluator/) | Python | Applies the agent's changes to a clean tree, grades them (build, proofs of concept, functional and intent tests) and writes `result.json`. |
| [`mcp/`](mcp/) | Python | The MCP server that gives the agent its `test_patch` tool, limited by the difficulty level. |
| [`plugins/`](plugins/) | Python, shell | Plugins that run before, during or after the agent and grading phases. `plugins.yaml` says which ones run. |

The daemon these call is in [`sdk/daemon`](../sdk/daemon/), and the Dockerfiles
that assemble them into the tool layer are in [`images/`](../images/).

Test them with `just test go python`. The container contract, the environment
variables, ports and files that agents and plugins rely on, is stable: see
[Extension points](../docs/guides/extension-points.md) before you change it.

- [Architecture](../docs/concepts/architecture.md) and
  [Grading pipeline](../docs/concepts/grading.md)
- [MCP server](../docs/reference/mcp-server.md)
- [Plugins and hooks](../docs/concepts/plugins-and-hooks.md) and
  [Write a plugin](../docs/guides/write-a-plugin.md)
