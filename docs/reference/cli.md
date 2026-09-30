---
outline: deep
---

# CLI

The `ssebench` command builds the images for a task and runs one agent on one
task with one model. From a clone of the repository, run it as
`uv run ssebench` in the repository root or any directory below it; see
[Working directory](#working-directory). Without a clone, run `uvx ssebench`
or install the package from PyPI; see [Without a clone](#without-a-clone).

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
| `ssebench dataset verify` | Grade tasks with the reference and dummy agents and check that they grade as sound tasks do |
| `ssebench tasks list` | List the tasks of a catalog or a local dataset |
| `ssebench proxy` | Start, rebuild or stop the local LiteLLM proxy |
| `ssebench init` | Write .env with generated secrets, models/ and results/ to the current directory |
| `ssebench demo up` | Start the demo stack, run one agent on one task and show the run in the web UI |
| `ssebench demo down` | Remove everything the demo created |
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

Before it starts the proxy or builds an image, `ssebench run` checks the
arguments: the agent must exist and have a valid `agent.yaml`, `--model` must be
defined in `models/*.yaml`, and `.env` must hold the provider key that the model
needs, except for the `dummy` and `reference` agents, which make no model calls.
Each failure is one line on standard error, with the valid choices where there
are some, and exit status 1. A failed image build ends the same way, after
Docker's own output.

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
| `--force` | off | Rebuild images even when they are up to date; without it, an image is rebuilt only when the task's files changed since it was built |

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

### `ssebench dataset verify`

Grades tasks end to end, each with two `ssebench run`s: the `reference` agent,
whose upstream fix must pass every check the task has, and the `dummy` agent,
whose unmodified project must build and pass its functional tests while every
proof of concept still triggers the bug. The dummy's intent tests should fail
too; when they pass, the summary warns that they do not check the fix. It
starts the [LiteLLM proxy](/concepts/litellm-proxy) once, like `ssebench run`,
and needs the base images of the tasks (`make -C images/base-images <name>`).

```sh
uv run ssebench dataset verify gjson-196-bf4efcb
uv run ssebench dataset verify --changed-since origin/main --jobs 4
```

It writes, under the output directory, one JSON file per task in `tasks/`, the
log of every run in `logs/`, the run directories in `runs/results/`, and
`summary.md` and `summary.json`, a table of every task result in the directory
by check. It exits 1 when a task does not grade as expected. The
[Dataset](https://github.com/42-b3yond-6ug/ssebench/blob/main/.github/workflows/dataset.yml)
workflow runs it for the tasks a pull request changes, and weekly for all of
them.

<!-- generated: cli dataset verify -->

```sh
ssebench dataset verify [-h] [--dir DIR] [--changed-since REV] [--list] [-j JOBS]
                        [-o OUTPUT] [--model MODEL] [--difficulty DIFFICULTY]
                        [--timeout TIMEOUT] [--retries RETRIES] [--summarize]
                        [TASK ...]
```

| Option | Default | Description |
|---|---|---|
| `TASK` | every task | Tasks to verify |
| `--dir DIR` | `datasets/pilot` in the SSEBench home | Dataset directory |
| `--changed-since REV` |  | Verify the tasks that changed since the merge base of REV and HEAD, including those whose base image changed under `images/base-images` |
| `--list` | off | Print the selected tasks and their base images as JSON; run nothing |
| `-j, --jobs JOBS` | `2` | Tasks to verify in parallel |
| `-o, --output OUTPUT` | `results/dataset-verify` | Output directory |
| `--model MODEL` | `claude-sonnet-4-6` | Model of the dummy runs, which make no model calls |
| `--difficulty DIFFICULTY` | `2` | Difficulty level of the runs |
| `--timeout TIMEOUT` | `3600` | Time limit of each run's agent and grading |
| `--retries RETRIES` | `0` | Times to repeat a run that ends without a result, as when a build loses the network |
| `--summarize` | off | Write the summary of the task results already in `OUTPUT/tasks/`; run nothing |

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

## `ssebench init`

Sets up the current directory as a workspace, the way `just setup` does in a
checkout. Run it once, in an empty directory, when you run `ssebench` from a
[package install](#without-a-clone).

```sh
ssebench init
```

<!-- generated: cli init -->

```sh
ssebench init [-h]
```

It takes no options.

<!-- end generated -->

It writes three things, and leaves each one alone if it already exists, so it is
safe to run again:

- `.env`, from the packaged `.env.example`, with a generated master key for the
  LiteLLM proxy and a generated password for its database. Only you can read
  the file. Add the keys of your model providers to it.
- `models/`, a copy of the model definitions in the package. `ssebench run` and
  `ssebench proxy up` build the proxy image from this directory, and rebuild it
  when you change a file; see [Add a model](/guides/add-a-model).
- `results/`, where runs write their results.

In a checkout, the workspace is the checkout, which already has `models/`, so
the command only writes `.env` and `results/`.

## `ssebench demo`

Starts, and removes, the [local demo](/getting-started/demo): the LiteLLM proxy
and its database, the task catalog and the web UI in a Compose project of their
own (`SSEBENCH_DEMO_PROJECT`, default `ssebench-demo`), and one run of an agent
that the web UI shows. `just demo` and `just demo-down` call it.

```sh
uv run ssebench demo up
```

<!-- generated: cli demo up -->

```sh
ssebench demo up [-h] [--task ID] [--agent NAME] [--model NAME] [--timeout SECONDS]
                 [--build]
```

| Option | Default | Description |
|---|---|---|
| `--task ID` | `gjson-196-bf4efcb` | Task ID, from the bundled pilot dataset; pick a fast one |
| `--agent NAME` | `reference` | Agent name, a directory under `agents/`; reference applies the task's known fix |
| `--model NAME` |  | Model name, as defined in `models/*.yaml`; required for every agent but reference |
| `--timeout SECONDS` | `3600` | How long the agent may run |
| `--build` | off | Build every image from this checkout instead of pulling the published ones |

<!-- end generated -->

`up` checks the host as `ssebench doctor` does, then pulls the images of the
catalog, the web UI and the task at this checkout's version, and builds those
that the registry does not have. The LiteLLM proxy image is always built from
`models/`, as `ssebench proxy up` does. It starts the stack, waits until the
proxy, the catalog and the web UI answer, and runs
`ssebench run --keep-container` in the background, because a kept container
keeps that command running. When the evaluator has graded the run, `up` checks
that the web UI shows it, prints the result and the address of the web UI, and
returns. The agent's `--model` needs its provider key in `.env`, and `up`
stops before it builds anything when the key is missing. Running `up` again
replaces the previous run.

The web UI listens on `127.0.0.1:3001` (`SSEBENCH_DEMO_WEBUI_PORT`), the catalog
on `127.0.0.1:8090` (`SSEBENCH_DEMO_CATALOG_PORT`) and the proxy on
`LITELLM_PORT`. The web UI container shares the host's network and mounts the
Docker socket, so the demo needs a Linux Docker engine, and its terminal is off
unless you set `SSEBENCH_WEBUI_TERMINAL=1`.

```sh
uv run ssebench demo down
```

<!-- generated: cli demo down -->

```sh
ssebench demo down [-h]
```

It takes no options.

<!-- end generated -->

`down` removes the containers of runs on the demo's networks, then the Compose
project with its database volume. It touches nothing else: not the stack you
run with `just launch`, not other containers, not the images and not `results/`.
It refuses to work on a Compose project that has containers the demo did not
create.

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
3. the repository the CLI was installed from, for an editable install;
4. the copy of these directories that the `ssebench` package carries; see
   [Without a clone](#without-a-clone).

From outside the repository, run `uv run --project /path/to/ssebench ssebench ...`
or set `SSEBENCH_HOME`. The CLI reads `.env` in the workspace; variables set in
the environment take precedence over it. Paths you pass, such as `--local`,
`--catalog` and `--benchmarks`, are relative to the working directory, and so
is `results/`.

The *workspace* holds what you edit and what runs produce: `.env`, `models/`
and `results/`. In a checkout it is the SSEBench home. Without a clone it is
the working directory, so run `ssebench` from the directory that
`ssebench init` set up.

## Without a clone

`ssebench` runs from the wheel alone, as `uvx ssebench` or after
`pip install ssebench`. A checkout, or `SSEBENCH_HOME`, still takes precedence
when there is one.

The wheel carries, under `ssebench/_data/` and laid out like the repository:

- the agent definitions in `agents/`, with their Dockerfiles;
- `models/` and the Compose file with the LiteLLM image's sources;
- the tool layer Dockerfiles, the sources of the SDK, the evaluator and the MCP
  server, `uv.lock`, and `runtime/plugins/`;
- the pilot manifest, `datasets/pilot/manifest.json`, but not the task folders.

What a run needs beyond that comes from the registry and the network:

- The task's **case image** is pulled from
  `$SSEBENCH_REGISTRY/case/<dataset>/<task>`. Without a task folder to build
  it from, a failed pull ends the run.
- The **tool layer** and the **agent image** are built on top of the case
  image from the packaged files, as in a checkout. The daemon and the
  entrypoint, which need Rust and Go to build, come from the published
  `runtime` image of the same version, passed as `--build-context
  runtime=docker-image://$SSEBENCH_REGISTRY/runtime:<version>`. The Python
  environments of the evaluator and the MCP server are built from the packaged
  `uv.lock`, which downloads packages.
- The **proxy image** is built from the packaged Dockerfile with the models in
  the workspace's `models/`, and rebuilt when they change.

Commands that read task folders, such as `ssebench build-case` and
`ssebench dataset validate` without a directory, need a checkout or an explicit
directory.

