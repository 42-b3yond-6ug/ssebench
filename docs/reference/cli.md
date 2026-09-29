---
outline: deep
---

# CLI

The `ssebench` command builds the images for a task and runs one agent on one
task with one model. From a clone of the repository, run it as
`uv run ssebench` in the repository root or any directory below it; see
[Working directory](#working-directory).

`ssebench --version` prints the SSEBench version, which is also the tag of the
tool layer and agent images the CLI builds; see
[Releasing and versioning](/contributing/releasing).

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
| `--tool-layer NAME` | `sandbox` | The [tool layer](/guides/extension-points#tool-layers) to build, in sandbox mode; installed extensions can add more |
| `--timeout SECONDS` | `3600` | How long the agent may run |
| `--difficulty LEVEL` | `2` | Which checks the agent's `test_patch` tool may run, from 0 to 4; see [Difficulty levels](/reference/mcp-server#difficulty-levels) |
| `--keep-container` | off | Keep the container after the run, for example to inspect it from the [web UI](/webui/) |

Either `--local` or a catalog (`--catalog` or `SSEBENCH_CATALOG`) is required.

In order, `run`:

1. starts the [LiteLLM proxy](/concepts/litellm-proxy) if it is not running,
   rebuilding its image first when `models/` changed, and waits for it to
   become healthy;
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

## `ssebench dataset`

Checks a dataset and writes the files generated from it. See
[Dataset manifest](/dataset/manifest) for the layout, the task config and the
manifest these commands work with. Each command exits 1 when it fails.

```sh
uv run ssebench dataset validate
uv run ssebench dataset manifest --check
```

| Command | Description |
|---------|-------------|
| `validate [DIR]` | Check every task folder: the config against the schema, the ID against the folder name, the Dockerfile's base image, and that every path in the config is a file the Dockerfile copies into the image. Lists every problem, per task |
| `manifest [DIR]` | Validate the dataset and write its `manifest.json` |
| `schema` | Write the JSON Schemas of the task config, `dataset.yaml` and the manifest |

`DIR` is the dataset directory and defaults to `datasets/pilot` in the
[SSEBench home](#working-directory).

| Option | Command | Default | Description |
|--------|---------|---------|-------------|
| `-o FILE` | `manifest` | `DIR/manifest.json` | Output file, or `-` for standard output |
| `--generated-from COMMIT` | `manifest` | none | Record the repository commit the manifest is generated from |
| `-o DIR` | `schema` | `datasets/schema` in the SSEBench home | Output directory |
| `--check` | `manifest`, `schema` | off | Write nothing, and fail if the files are missing or out of date. `manifest --check` keeps the commit the file records |

## `ssebench proxy`

Starts, rebuilds or stops the local [LiteLLM proxy](/concepts/litellm-proxy),
the Compose stack in `deploy/compose/`. `just launch` and `just stop` call it.

```sh
uv run ssebench proxy up
```

| Argument | Description |
|----------|-------------|
| `up` | Build the proxy image if it is missing or older than `models/`, start the stack, and wait until the proxy is healthy |
| `build` | Only build the proxy image, if it is missing or older than `models/` |
| `down` | Stop the stack; its database volume is kept |
| `--rebuild` | With `up` or `build`, rebuild the image even if it is current |

The image is tagged with the SSEBench version and carries a hash of
`models/*.yaml` and `images/litellm/` in its `ssebench.litellm-config` label,
which is how `up`, `build` and `ssebench run` tell that it is out of date. The
stack's Compose project is `COMPOSE_PROJECT_NAME` (default `ssebench`), and the
proxy listens on `LITELLM_PORT` (default 4000); see
[SSEBench settings](/reference/environment#ssebench-settings).

## `ssebench doctor`

Checks that the host can build images and run benchmarks, and prints a fix for
each problem it finds.

```sh
uv run ssebench doctor
```

It checks Docker, buildx and Compose, the free disk space where Docker keeps
its images, the CPU architecture (many pilot tasks build amd64-only images),
`.env` and the proxy secrets in it, whether the LiteLLM proxy answers on its
port, and which provider keys that `models/*.yaml` refers to are set. It exits
with status 1 when a required check fails; warnings do not change the exit
status.

## Commands from extensions

Installed packages can add subcommands; `ssebench --help` lists them. See
[Extension points](/guides/extension-points#commands).

## Working directory

The CLI finds `agents/`, `images/`, `runtime/`, `datasets/` and the Compose
file in the *SSEBench home*, which is the first of:

1. the directory in `SSEBENCH_HOME`;
2. the nearest directory at or above the working directory whose
   `pyproject.toml` has a `[tool.ssebench]` table, which is the repository
   root;
3. the repository the CLI was installed from, for an editable install.

From outside the repository, run `uv run --project /path/to/ssebench ssebench ...`
or set `SSEBENCH_HOME`. The CLI reads `.env` in the SSEBench home; variables
set in the environment take precedence over it. Paths you pass, such as `--local` and `--benchmarks`,
are relative to the working directory, and so is `results/`.
