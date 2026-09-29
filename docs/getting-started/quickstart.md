---
outline: deep
---

# Quickstart

This guide sets up SSEBench on your machine and runs one agent on one task from the `pilot` dataset.

## Quick Start

1. **Build the base images**

   ```bash
   just base-images
   ```

   This builds the C, Go and Rust toolchain images that every pilot task starts from.

2. **Start the LiteLLM proxy**

   ```bash
   just launch
   ```

   This builds and starts the Docker Compose stack in `deploy/compose/docker-compose.yaml`: the LiteLLM proxy on port 4000 and its Postgres database.

3. **Run a task**

   ```bash
   uv run ssebench run \
       --local datasets/pilot \
       --task generic-c-jq-jq_gh_3196 \
       --agent claude-code \
       --model claude-sonnet-4-5
   ```

   The first run of a task builds its case, tool and agent images, which can take a while.

::: tip
Use `--agent dummy` to check the pipeline end to end. The dummy agent exits immediately and makes no model calls, so the evaluator grades the unmodified source tree.
:::

## Results

Each run writes to `results/<task>/<model>/<agent>/`:

- `result.json`: the evaluator's grade;
- `dialog.jsonl`: the agent's session, in the [dialog protocol](/reference/dialog-protocol) format;
- a snapshot of the final source tree, and the logs of every component.

A summary of the run is also written to `results/<task>-<agent>-<model>.json`.

## Next Steps

- [Architecture](/concepts/architecture) - Understand the system design
- [Adding Models](/guides/add-a-model) - Integrate new LLM models
- [MCP Server](/reference/mcp-server) - The `test_patch` tool and difficulty levels
- [Project Structure](/contributing/project-structure) - Repository layout
