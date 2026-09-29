---
outline: deep
---

# CLI

## `ssebench run`

| Argument | Default | Description |
|----------|---------|-------------|
| `--model` | *(required)* | Model name, as defined in `models/*.yaml` |
| `--agent` | *(required)* | Agent name, a directory under `agents/` |
| `--task` | *(required)* | Task ID, the name of the task's folder |
| `--local PATH` | | Dataset directory that contains the task folder, e.g. `datasets/pilot` |
| `--mode` | `sandbox` | Execution mode: `sandbox` or `sidecar` |
| `--timeout` | `3600` | Agent timeout in seconds |
| `--difficulty` | `2` | Which checks the agent's `test_patch` tool may run (0-4); see [Difficulty Levels](/reference/mcp-server#difficulty-levels) |
| `--keep-container` | off | Keep the container after the run, for example to inspect it from the Web UI |

`uv run ssebench build-case --benchmarks <dataset-dir> [--tasks a,b] [--force]` builds only the case images of a dataset.
