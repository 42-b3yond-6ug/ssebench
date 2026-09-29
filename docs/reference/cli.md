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
[Releasing and versioning](/contributing/releasing). `ssebench <command> --help`
prints the options of a command.

<!-- The usage blocks and option tables are generated from the CLI's argparse
parser by tools/docs/reference.py; change the help strings in
bench/src/ssebench/cli/, then run `just docs-gen`. -->

<!-- generated: cli commands -->

| Command | Description |
|---|---|
| `ssebench run` | Run a benchmark |
| `ssebench build-case` | Build case images |
| `ssebench dataset validate` | Check every task folder of a dataset against the task schema |
| `ssebench dataset manifest` | Validate a dataset and write its manifest.json |
| `ssebench dataset schema` | Write the JSON Schemas of the task config, dataset.yaml and the manifest |
| `ssebench tasks list` | List the tasks of a catalog or a local dataset |
| `ssebench proxy` | Start, rebuild or stop the local LiteLLM proxy |
| `ssebench doctor` | Check that this host can build and run benchmarks |

<!-- end generated -->

## `ssebench run`

Runs one agent × model × task combination and writes the
[results](/concepts/results) to `results/`.

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent <agent> --model <model>
```

<!-- generated: cli run -->

```sh
ssebench run [-h] [--model NAME] --agent NAME --task ID [--local DIR]
             [--catalog PATH|URL] [--mode MODE] [--tool-layer NAME] [--plugin NAME]
             [--timeout SECONDS] [--difficulty LEVEL] [--keep-container]
             [--egress POLICY]
```

| Option | Default | Description |
|---|---|---|
| `--model NAME` |  | Model name, as defined in `models/*.yaml`; required for every agent but reference, which uses none |
| `--agent NAME` | *(required)* | Agent name, a directory under `agents/` |
| `--task ID` | *(required)* | Task ID, the name of the task's folder |
| `--local DIR` |  | Dataset directory that contains the task folder, for example `datasets/pilot`; the case image is built from the folder |
| `--catalog PATH\|URL` | `$SSEBENCH_CATALOG`, else the bundled pilot manifest | Task catalog: a `manifest.json` path or URL, a dataset directory, or the URL of a catalog service; used when `--local` is not given |
| `--mode MODE` | `sandbox` | Execution mode: sandbox, or sidecar (experimental) |
| `--tool-layer NAME` | `sandbox` | Tool layer to build in sandbox mode; installed extensions can add more |
| `--plugin NAME` | `[]` | Run a plugin in this run (repeatable), instead of those `plugins.yaml` enables; sandbox mode only |
| `--timeout SECONDS` | `3600` | How long the agent may run |
| `--difficulty LEVEL` | 2 = `NO_FUTURE_TEST` | Which checks the agent's `test_patch` tool may run, from 0 (all) to 4 (none). One of 0, 1, 2, 3, 4 |
| `--keep-container` | off | Keep the container after the run, for example to inspect it from the web UI |
| `--egress POLICY` | `restricted` | Network egress of the run container: restricted reaches the LiteLLM proxy but not the internet; open also has internet access, for tasks that need network at test time |

<!-- end generated -->

`--model` is optional with `--agent reference`; see [Reference runs](#reference-runs).
`--mode` is explained in [Sandbox and sidecar](/concepts/sandbox-and-sidecar),
`--difficulty` in [Difficulty levels](/concepts/difficulty-levels), `--tool-layer`
in [Extension points](/guides/extension-points#tool-layers), and `--egress` in
[Integrity and egress](/deployment/integrity-and-egress); the egress policy is
recorded as `config.egress` in the run summary. `--keep-container` leaves the
container for the [web UI](/webui/) to inspect; in sidecar mode it leaves both
containers and their volumes.

Without `--local`, the task comes from the [task catalog](#task-catalog), and
its case image is pulled from `$SSEBENCH_REGISTRY`. When the pull fails, the CLI
says so and builds the image from the task's folder instead, if a copy of the
folder whose files match the catalog is available locally: next to a local
manifest, or in `datasets/<dataset>/` of the
[SSEBench home](#working-directory), as for the bundled pilot dataset.

In order, `run`:

1. starts the [LiteLLM proxy](/concepts/litellm-proxy) if it is not running,
   rebuilding its image first when `models/` changed, and waits for it to
   become healthy;
2. checks that the proxy knows the model, and creates a key for this run that
   can use only that model;
3. builds the case, tool and agent [image layers](/concepts/image-layers);
4. runs the task container, which runs the agent and then the evaluator. In
   sidecar mode, it starts the task container with the daemon, then runs the
   agent container, which runs the agent and then the evaluator, and removes
   the task container afterwards;
5. writes the grade, the run settings and the model spend to `results/`, and
   adds the run settings to the run's `result.json` as `config`.

### Reference runs

`--agent reference` runs the [`reference` agent](https://github.com/42-b3yond-6ug/ssebench/tree/main/agents/reference),
which applies the task's reference patch, the known upstream fix, instead of
asking a model for one. It checks the task and the grader rather than a model:
on a sound task, every check passes. It makes no model calls, so it needs no
provider key.

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent reference
```

A reference run differs from other runs in these ways:

- `--model` is optional. The run's model is `none`: no proxy key is created,
  the spend is 0, and the results go to `results/<task>/none/reference/` and
  `results/<task>-reference-none.json`. Any other `--model` is ignored, with a
  warning. The LiteLLM proxy still starts, as the container joins its network.
- `run` copies the file that `files.patch` names out of the case image and
  mounts it read-only at `/reference/patch.diff` in the container (in sidecar
  mode, the agent container). No other agent gets this mount. A task without
  `files.patch` cannot be run this way.
- `result.json` and the summary record `config.reference_run: true`, the
  container carries the label `ssebench.reference-run=true`, the web UI marks
  the result as a reference run, and `just report` leaves reference runs out
  of the scores.

## `ssebench tasks list`

Lists the tasks of a catalog or of a local dataset. It reads nothing over the
network unless the catalog is a URL, so it works offline with the bundled pilot
manifest.

```sh
uv run ssebench tasks list
uv run ssebench tasks list --json --catalog https://catalog.example.org
```

<!-- generated: cli tasks list -->

```sh
ssebench tasks list [-h] [--catalog PATH|URL | --local DIR] [--json]
```

| Option | Default | Description |
|---|---|---|
| `--catalog PATH\|URL` | `$SSEBENCH_CATALOG`, else the bundled pilot manifest | Task catalog: a `manifest.json` path or URL, a dataset directory, or the URL of a catalog service |
| `--local DIR` |  | Dataset directory: list its task folders instead |
| `--json` | off | Print a JSON array of the tasks without files and metadata, with image names prefixed by the registry |

<!-- end generated -->

Without `--json`, it prints a table of task IDs, languages and projects. With
`--json`, it prints the tasks as the
[catalog service](/dataset/manifest#catalog-service) returns them from
`GET /tasks`.

## Task catalog

A catalog is a [dataset manifest](/dataset/manifest). `--catalog`, or the
`SSEBENCH_CATALOG` [setting](/reference/environment#ssebench-settings) when the
option is not given, names it as one of:

| Value | Manifest read |
|-------|---------------|
| path of a file, such as `datasets/pilot/manifest.json` | the file |
| path of a directory, such as `datasets/pilot` | `manifest.json` in it |
| `http(s)` URL whose path ends in `.json` | the URL |
| any other `http(s)` URL, such as a [catalog service](/dataset/manifest#catalog-service) at `http://localhost:8080` | `manifest.json` under it |

With neither, the catalog is `datasets/pilot/manifest.json` in the
[SSEBench home](#working-directory), the pilot dataset's manifest that ships
with SSEBench. The [web UI](/webui/) reads the same variable and passes its
catalog on to the runs it launches.

## `ssebench build-case`

Builds the case images of a dataset without running anything.

```sh
uv run ssebench build-case --benchmarks datasets/pilot --tasks gjson-196-bf4efcb
```

<!-- generated: cli build-case -->

```sh
ssebench build-case [-h] [--benchmarks DIR] [--tasks IDS] [--force]
```

| Option | Default | Description |
|---|---|---|
| `--benchmarks DIR` | `datasets/pilot` in the SSEBench home | Dataset directory |
| `--tasks IDS` | every task | Comma-separated task IDs |
| `--force` | off | Rebuild images that already exist |

<!-- end generated -->

## `ssebench dataset`

Checks a dataset and writes the files generated from it. See
[Dataset manifest](/dataset/manifest) for the layout, the task config and the
manifest these commands work with. Each command exits 1 when it fails.

```sh
uv run ssebench dataset validate
uv run ssebench dataset manifest --check
```

### `ssebench dataset validate`

Checks every task folder: the config against the schema, the ID against the
folder name, the Dockerfile's base image, and that every path in the config is
a file the Dockerfile copies into the image. Lists every problem, per task.

<!-- generated: cli dataset validate -->

```sh
ssebench dataset validate [-h] [DIR]
```

| Option | Default | Description |
|---|---|---|
| `DIR` | `datasets/pilot` in the SSEBench home | Dataset directory |

<!-- end generated -->

### `ssebench dataset manifest`

Validates the dataset and writes its `manifest.json`. `--check` keeps the
commit the file records.

<!-- generated: cli dataset manifest -->

```sh
ssebench dataset manifest [-h] [-o FILE] [--check] [--generated-from COMMIT] [DIR]
```

| Option | Default | Description |
|---|---|---|
| `DIR` | `datasets/pilot` in the SSEBench home | Dataset directory |
| `-o, --output FILE` | `manifest.json` in the dataset | Output file, or - for stdout |
| `--check` | off | Fail if the file is out of date; write nothing |
| `--generated-from COMMIT` | none; with `--check`, the commit recorded in the file | Record the repository commit the manifest is generated from |

<!-- end generated -->

### `ssebench dataset schema`

Writes the JSON Schemas of the task config, `dataset.yaml` and the manifest,
which [Configuration files](/reference/configuration) describes.

<!-- generated: cli dataset schema -->

```sh
ssebench dataset schema [-h] [-o DIR] [--check]
```

| Option | Default | Description |
|---|---|---|
| `-o, --output DIR` | `datasets/schema` in the SSEBench home | Output directory |
| `--check` | off | Fail if the files are out of date; write nothing |

<!-- end generated -->

## `ssebench proxy`

Starts, rebuilds or stops the local [LiteLLM proxy](/concepts/litellm-proxy),
the Compose stack in `deploy/compose/`. `just launch` and `just stop` call it.

```sh
uv run ssebench proxy up
```

<!-- generated: cli proxy -->

```sh
ssebench proxy [-h] [--rebuild] ACTION
```

| Option | Default | Description |
|---|---|---|
| `ACTION` | *(required)* | up: build the proxy image if it is missing or older than `models/`, start the stack and wait until the proxy is healthy; build: only build the image, if it is missing or older than `models/`; down: stop the stack and keep its database volume |
| `--rebuild` | off | With up or build, rebuild the proxy image even if it is current |

<!-- end generated -->

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

<!-- generated: cli doctor -->

```sh
ssebench doctor [-h]
```

It takes no options.

<!-- end generated -->

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
set in the environment take precedence over it. Paths you pass, such as
`--local`, `--catalog` and `--benchmarks`, are relative to the working
directory, and so is `results/`.
