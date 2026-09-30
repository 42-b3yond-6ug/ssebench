# agents

One folder per agent. An agent is the layer that goes on top of the tool layer
of a run; `ssebench run --agent <name>` builds it from its folder.

| Agent | What it is |
|---|---|
| [`claude-code/`](claude-code/) | Anthropic's Claude Code. |
| [`codex/`](codex/) | OpenAI's Codex CLI. |
| [`opencode/`](opencode/) | The open-source OpenCode agent. |
| [`dummy/`](dummy/) | Does nothing and makes no model calls; a run with it grades the untouched source, so its patch fails. It tests the pipeline. |
| [`reference/`](reference/) | Applies the task's known fix and makes no model calls; a sound task passes every check. It checks a task, and powers `just demo`. Its runs never count as a model's score. |

Each folder has an `agent.yaml` (the agent's name), a `Dockerfile` and, for
every agent but `dummy`, a wrapper `<name>-sse/`. The wrapper is a Python project
that starts the agent, reads the task through the `sse` SDK and writes
`dialog.jsonl`; every wrapper is a member of the repository's uv workspace. An
agent never talks to a model provider directly: all LLM traffic goes through the
LiteLLM proxy, at the endpoint the run passes in `SSE_BASE_URL`.

To add an agent, follow [Add an agent](../docs/guides/add-an-agent.md).

- [Dialog protocol](../docs/reference/dialog-protocol.md): the format of
  `dialog.jsonl`
- [Reference runs](../docs/reference/cli.md#reference-runs)
- [Image layers](../docs/concepts/image-layers.md)
