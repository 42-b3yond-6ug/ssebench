---
outline: deep
---

# What is SSEBench?

SSEBench (Software Security Evaluation Benchmark) measures how well AI coding
agents fix real security vulnerabilities.

Every task is a publicly disclosed bug in an open-source C, Go or Rust project,
paired with its upstream fix. SSEBench drops an agent into a Docker container
with the vulnerable source tree and a tool for building and testing it, lets it
work until it stops or times out, and then grades the patch it leaves behind:
does the project still build, does the proof of concept stop reproducing, and do
the project's tests pass, including the tests that came with the upstream fix?

## What you can measure

- **Agents.** Run Claude Code, Codex, OpenCode or your own agent on the same
  tasks and compare how they plan, use tools and verify their fixes.
- **Models.** Run one agent against different models. Agents and models are
  decoupled, so any agent can use any model.
- **Settings.** The [difficulty level](/concepts/difficulty-levels) controls
  how much checking the agent may do while it works, so you can see how much an
  agent relies on test feedback.

Each run produces a graded `result.json`, the agent's full dialog, a snapshot of
the final source tree and the logs of every component. A report can be built
from the results of many runs.

## Key features

### Docker-based infrastructure

Every run happens in Docker containers, which gives:

- isolated, reproducible environments;
- the same toolchain and dependencies for every run of a task;
- a clean copy of the project for every run.

### LiteLLM proxy

Agents never talk to a model provider directly. Every LLM request goes through
a [LiteLLM proxy](/concepts/litellm-proxy), which:

- lets you switch models without changing the agent;
- supports the many providers LiteLLM supports;
- gives each run its own key and records what the run spent.

### Layered images

The container image for a run is assembled from four
[layers](/concepts/image-layers):

| Layer | Contents |
|-------|----------|
| **Base** | Toolchain for the task's language (C, Go or Rust), shared across tasks |
| **Case** | The project at the vulnerable commit, with its build dependencies and the task's scripts |
| **Tool** | The SSEBench runtime: entrypoint, daemon, SDK, MCP server and evaluator |
| **Agent** | The agent under test |

## Supported agents

- **Claude Code**: Anthropic's command-line coding agent.
- **Codex**: OpenAI's command-line coding agent.
- **OpenCode**: an open-source terminal coding agent.
- **dummy**: does nothing and makes no model calls; for testing the pipeline.

To bring your own, see [Add an agent](/guides/add-an-agent).

## Next steps

- [Installation](/getting-started/installation): set up SSEBench on your machine
- [Quickstart](/getting-started/quickstart): run an agent on a pilot task
- [Architecture](/concepts/architecture): how SSEBench works
- [The pilot dataset](/dataset/pilot): the tasks that ship with SSEBench
