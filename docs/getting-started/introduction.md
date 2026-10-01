---
outline: deep
---

# What is SSEBench?

SSEBench is a framework of reinforcement-learning environments for AI coding
agents on real security vulnerabilities, with verifiable rewards. The same
environments make a benchmark.

Every task is a publicly disclosed bug in an open-source C, Go or Rust project,
paired with its upstream fix, and packaged as a self-contained Docker
environment. SSEBench drops an agent into the container with the vulnerable
source tree and a tool for building and testing it, lets it work until it stops
or times out, and then grades the patch it leaves behind: does the project still
build, does the proof of concept stop reproducing, and do the project's tests
pass, including the tests that came with the upstream fix? The grade comes from
running code, not from a judge model.

## Environments, episodes and rewards

| SSEBench | Reinforcement learning |
|---|---|
| a [task](/concepts/tasks-and-datasets): case image, build, PoC and test scripts, hidden tests | environment |
| a model driving an agent harness (Claude Code, Codex, OpenCode, your own) | policy |
| the issue or crash report the agent receives | initial observation |
| one run of agent × model × task | episode (rollout) |
| the `test_patch` tool, gated by the [difficulty level](/concepts/difficulty-levels) | feedback during the episode |
| `result.json`: build, each PoC, functional tests, intent tests ([grading](/concepts/grading)) | reward |

Each run also records the agent's full dialog, a snapshot of the final source
tree and the logs of every component, so an episode can be inspected after the
fact.

## Rewards the policy cannot game

Nothing the agent can reach while it works reveals the reference patch, the
hidden tests or the upstream fix, and nothing it does changes how it is graded:

- the agent runs as an unprivileged user; the reference patch, the hidden tests
  and the grade are readable only by root;
- the project's git history is replaced by a single commit, so the fix cannot
  be recovered from `git log`;
- the task's scripts run as a third user in a scratch copy of the project, and
  every process the agent left running is killed before grading;
- intent tests, the upstream tests that came with the fix, reject patches that
  only silence the proof of concept;
- a bypass suite (`tests/integrity/`) attacks these defenses from inside a run.

See [the integrity model](/concepts/integrity).

## What you can do with it

- **Train.** Use the tasks as environments and `result.json` as the reward for
  a policy that repairs vulnerabilities.
- **Compare agents.** Run Claude Code, Codex, OpenCode or your own agent on the
  same tasks and compare how they plan, use tools and verify their fixes.
- **Compare models.** Run one agent against different models. Agents and models
  are decoupled, so any agent can use any model.
- **Vary the feedback.** The [difficulty level](/concepts/difficulty-levels)
  controls how much checking the agent may do while it works, so you can see
  how much an agent relies on test feedback.

A report can be built from the results of many runs.

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
- **reference**: applies the task's known fix and makes no model calls; its
  runs check a task, and never count as a model's score. See
  [Reference runs](/reference/cli#reference-runs).

To bring your own, see [Add an agent](/guides/add-an-agent).

## Next steps

- [Quickstart](/getting-started/quickstart): clone and set up SSEBench, and run your first task
- [Try without installing](/getting-started/try): run the demo and a pilot task, with no clone
- [Architecture](/concepts/architecture): how SSEBench works
- [The pilot dataset](/dataset/pilot): the tasks that ship with SSEBench
