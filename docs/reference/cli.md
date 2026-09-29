---
outline: deep
---

# CLI

The `ssebench` command builds the images for a task and runs one agent on one
task with one model. From a clone of the repository, run it as
`uv run ssebench` in the repository root or any directory below it; see
[Working directory](#working-directory).

## `ssebench run`

Runs one agent × model × task combination and writes the
[results](/concepts/results) to `results/`.

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent <agent> --model <model>
```

| Option | Default | Description |
|--------|---------|-------------|
| `--model NAME` | *(required)* | Model name, as defined in `models/*.yaml` |
| `--agent NAME` | *(required)* | Agent name, a directory under `agents/` |
| `--task ID` | *(required)* | Task ID, the name of the task's folder |
| `--local DIR` | | Dataset directory that contains the task folder, for example `datasets/pilot` |
| `--catalog URL` | `$SSEBENCH_CATALOG` | Catalog server to get the task from when `--local` is not given |
| `--mode MODE` | `sandbox` | Execution mode: `sandbox`, or `sidecar` (experimental); see [Sandbox and sidecar](/concepts/sandbox-and-sidecar) |
| `--timeout SECONDS` | `3600` | How long the agent may run |
| `--difficulty LEVEL` | `2` | Which checks the agent's `test_patch` tool may run, from 0 to 4; see [Difficulty levels](/reference/mcp-server#difficulty-levels) |
| `--keep-container` | off | Keep the container after the run, for example to inspect it from the [web UI](/webui/) |

Either `--local` or a catalog (`--catalog` or `SSEBENCH_CATALOG`) is required.

In order, `run`:

1. starts the [LiteLLM proxy](/concepts/litellm-proxy) if it is not running,
   and waits for it to become healthy;
2. checks that the proxy knows the model, and creates a key for this run that
   can use only that model;
3. builds the case, tool and agent [image layers](/concepts/image-layers);
4. runs the task container, which runs the agent and then the evaluator;
5. writes the grade, the run settings and the model spend to `results/`.

## `ssebench build-case`

Builds the case images of a dataset without running anything.

```sh
uv run ssebench build-case --benchmarks datasets/pilot --tasks gjson-196-bf4efcb
```

| Option | Default | Description |
|--------|---------|-------------|
| `--benchmarks DIR` | `datasets/pilot` in the [SSEBench home](#working-directory) | Dataset directory |
| `--tasks IDS` | every task | Comma-separated task IDs |
| `--force` | off | Rebuild images that already exist |

## Working directory

The CLI finds `agents/`, `images/`, `runtime/`, `datasets/` and the Compose
file in the *SSEBench home*, which is the first of:

1. the directory in `SSEBENCH_HOME`;
2. the nearest directory at or above the working directory whose
   `pyproject.toml` has a `[tool.ssebench]` table, which is the repository
   root;
3. the repository the CLI was installed from, for an editable install.

From outside the repository, run `uv run --project /path/to/ssebench ssebench ...`
or set `SSEBENCH_HOME`. Paths you pass, such as `--local` and `--benchmarks`,
are relative to the working directory, and so is `results/`.
