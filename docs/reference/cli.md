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
| `ssebench dataset schema` | Write the JSON Schemas of the task config, dataset.yaml, the manifest and the images lock |
| `ssebench dataset verify` | Grade tasks with the reference and dummy agents and check that they grade as sound tasks do |
| `ssebench dataset publish` | Push the case images of verified tasks to a registry |
| `ssebench dataset lock` | Write the images lock, which pins the published case images by digest |
| `ssebench tasks list` | List the tasks of a catalog or a local dataset |
| `ssebench runs list` | List the runs that exist on the backend, running or not |
| `ssebench runs inspect` | Show one run on the backend |
| `ssebench runs logs` | Print the output of a run's container |
| `ssebench runs stop` | Stop a run's container, leaving it in place |
| `ssebench runs remove` | Remove a run's containers and volumes, running or not |
| `ssebench runs endpoint` | Print the URL at which a port of a running run can be reached from here |
| `ssebench runs exec` | Run a command in a run's container |
| `ssebench runs results` | List the finished runs in results/, whether or not they still have containers |
| `ssebench proxy` | Start, rebuild or stop the local LiteLLM proxy |
| `ssebench init` | Write .env with generated secrets, models/ and results/ to the current directory |
| `ssebench demo up` | Start the demo stack, run one agent on one task and show the run in the web UI |
| `ssebench demo down` | Remove everything the demo created |
| `ssebench doctor` | Check that this host can build and run benchmarks |

<!-- end generated -->

## `ssebench run`

Runs one agent × model × task combination and writes the
[results](/concepts/results) to a directory of its own,
`results/<task>/<model>/<agent>/<run-id>/`.

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent <agent> --model <model>
```

<!-- generated: cli run -->

```sh
ssebench run [-h] [--model NAME] --agent NAME --task ID [--local DIR]
             [--catalog PATH|URL] [--build] [--mode MODE] [--backend NAME] [--prebuilt]
             [--tool-layer NAME] [--plugin NAME] [--run-id ID] [--require-pass]
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
| `--build` | off | Build the task's case image from its folder instead of pulling the published one; needs a checkout or `--catalog` with the task folder next to it. With `--local` the image is always built |
| `--mode MODE` | `sandbox` | Execution mode: sandbox, or sidecar (experimental) |
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | Where the run's containers execute: docker or kubernetes; installed extensions can add more. kubernetes needs `--prebuilt` |
| `--prebuilt` | off | Use the published agent images of the task under `$SSEBENCH_REGISTRY`, pulling them, instead of building the case, tool and agent layers; excludes `--tool-layer`, `--plugin` and `--build`. Also enabled by `SSEBENCH_PREBUILT`=1 |
| `--tool-layer NAME` | `sandbox` | Tool layer to build in sandbox mode; installed extensions can add more |
| `--plugin NAME` | `[]` | Run a plugin in this run (repeatable), instead of those `plugins.yaml` enables; sandbox mode only |
| `--run-id ID` |  | Name the run: its directory is `results/TASK/MODEL/AGENT/ID`, and its containers get the label `ssebench.run-id=ID`, so a tool that starts the run can find them. 1 to 64 letters, digits, '.', '_' or '-', and not `latest`. The run is refused if that directory exists. Default: the UTC time the command started and six random hex digits, such as 20260929-153012-a1b2c3 |
| `--require-pass` | off | Exit with status 1 unless the run's grade is passed, which needs every check the task has to pass; without it the command exits 0 whatever the grade. The grade is printed either way |
| `--timeout SECONDS` | `3600` | How long the agent may run |
| `--difficulty LEVEL` | 2 = `NO_FUTURE_TEST` | Which checks the agent's `test_patch` tool may run, from 0 (all) to 4 (none). One of 0, 1, 2, 3, 4 |
| `--keep-container` | off | Keep the container after the run, for example to inspect it from the web UI |
| `--egress POLICY` | `$SSEBENCH_EGRESS`, else restricted | Network egress of the run container: restricted reaches the LiteLLM proxy but not the internet; open also has internet access, for tasks that need network at test time |

<!-- end generated -->

`--model` is optional with `--agent reference`; see [Reference runs](#reference-runs).
`--mode` is explained in [Sandbox and sidecar](/concepts/sandbox-and-sidecar),
`--difficulty` in [Difficulty levels](/concepts/difficulty-levels), `--tool-layer`
in [Extension points](/guides/extension-points#tool-layers), `--backend` in
[Runner backends](/concepts/runner-backends), `--prebuilt` in
[Prebuilt images](/concepts/runner-backends#prebuilt-images), and `--egress` in
[Integrity and egress](/deployment/integrity-and-egress); the egress policy is
recorded as `config.egress` in the run summary. `--keep-container` leaves the
container for the [web UI](/webui/) to inspect; in sidecar mode it leaves both
containers and their volumes. `--run-id` names the run directory; without it the
CLI makes an ID, so running a combination again adds a run and replaces none;
see [Run IDs and repeated runs](/concepts/results#run-ids-and-repeated-runs).

Before it starts the proxy or builds an image, `ssebench run` checks the
arguments: the agent must exist and have a valid `agent.yaml`, `--model` must be
defined in `models/*.yaml`, and `.env` must hold the provider key that the model
needs, except for the `dummy` and `reference` agents, which make no model calls.
Each failure is one line on standard error, with the valid choices where there
are some, and exit status 1. A failed image build ends the same way, after
Docker's own output.

Without `--local`, the task comes from the [task catalog](#task-catalog), and
its [case image is pulled](#case-images) from `$SSEBENCH_REGISTRY`. When the
pull fails, the CLI says so and builds the image from the task's folder
instead, if a copy of the folder whose files match the catalog is available
locally: next to a local manifest, or in `datasets/<dataset>/` of the
[SSEBench home](#working-directory), as for the bundled pilot dataset.
`--build` skips the pull and builds the image from that folder, and fails
before starting anything when there is no such folder. With `--local` the image
is always built, so `--build` changes nothing.

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
5. writes the grade, the run settings and the model spend to `summary.json` in
   the run directory, and adds the run settings to the run's `result.json` as
   `config`.

Every image and container of a run uses the platform of the task's case image:
the host's architecture if the task's manifest `arch` lists it, otherwise the
first architecture listed. When that is not the host's, as for a `pilot` task
on an arm64 host, `run` warns once, before it starts anything, that the task
runs under emulation. See [Architectures](/deployment/host#architectures).

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
  the spend is 0, and the results go to
  `results/<task>/none/reference/<run-id>/`. Any other `--model` is ignored,
  with a warning. The LiteLLM proxy still starts, as the container joins its
  network.
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
| `--json` | off | Print a JSON array of the tasks without files and metadata, with image names prefixed by the registry and the case image tagged with the dataset version, or named by its digest when the images lock pins it |

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

### Case images

The case image of each task is published under the name the manifest gives it,
prefixed with `$SSEBENCH_REGISTRY`, and tagged with the dataset's version:
`ghcr.io/42-b3yond-6ug/ssebench/case/pilot/gjson-196-bf4efcb:pilot-v1`. Each
push also has a tag that names the commit it was built and verified at, such as
`pilot-v1-0123abc`, which no later commit reuses. Only the images that passed
[`ssebench dataset verify`](#ssebench-dataset-verify) are published, and they
are the images that it graded. They are for `linux/amd64` only.

`ssebench run` without `--local` pulls the image, so that a machine runs any
task without building it. It pulls:

- **by digest**, when an `images.lock.json` pins the task. The lock is the file
  of that name next to a local manifest, which is `datasets/pilot/` for the
  bundled catalog, or the path or URL that `SSEBENCH_IMAGES_LOCK` names. An
  entry applies when the lock's dataset version is the manifest's and the
  entry was built from the task files that the manifest lists; otherwise the
  CLI logs a warning and pulls by tag. The wheel carries the pilot lock, so a
  release runs the images it was published with. The digest identifies the
  image whatever registry serves it, so a mirror that copied the images with
  their digests can be used with `SSEBENCH_REGISTRY`.
- **by tag** (the dataset version) for a task the lock does not pin, for a
  dataset without a lock, and for a catalog service URL.

After a pull by digest, the image also gets the tag name locally, so that the
layers built on it and the [reference patch](#reference-runs) use exactly that
image. [Releasing and versioning](/contributing/releasing#case-images) describes
how the lock is refreshed, and the [pilot dataset](/dataset/pilot#prebuilt-images)
lists the size of every image.

## `ssebench runs`

Finds, watches, stops and removes runs through the [runner
backend](/concepts/runner-backends), and lists finished runs. A run is named by
its run ID, the value of `--run-id`. The [web UI](/webui/) drives these commands
with `--json`, so it works with every backend; they are as useful by hand:

```sh
uv run ssebench runs list
uv run ssebench runs logs --follow 20260929-153012-a1b2c3
uv run ssebench runs stop 20260929-153012-a1b2c3
```

Every command that takes a run ID exits with status 3 if no run has it, and 4 if
several runs do, which `--run-id` allows across different tasks, models and
agents. The commands other than `results` use the backend that `--backend`, or
`SSEBENCH_BACKEND`, names.

### `ssebench runs list`

<!-- generated: cli runs list -->

```sh
ssebench runs list [-h] [--backend NAME] [--json]
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `--json` | off | Print JSON instead of text |

<!-- end generated -->

`--json` prints one object: `backend` (its name), `supports_exec` (whether it can
run commands in a run), and `runs`, newest first. Each run has `run_id`, `name`,
`state` (`created`, `running`, `exited` or `unknown`), `exit_code`, `image`,
`created_at`, `task`, `model`, `agent`, `reference_run`, `results_dir` and the
run's `ssebench.*` labels. The container's environment, which holds the run's
key, is never part of it.

### `ssebench runs inspect`

<!-- generated: cli runs inspect -->

```sh
ssebench runs inspect [-h] [--backend NAME] [--json] RUN_ID
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `--json` | off | Print JSON instead of text |
| `RUN_ID` | *(required)* | The run's ID |

<!-- end generated -->

### `ssebench runs logs`

<!-- generated: cli runs logs -->

```sh
ssebench runs logs [-h] [--backend NAME] [--follow] RUN_ID
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `RUN_ID` | *(required)* | The run's ID |
| `--follow` | off | Keep printing until the container exits |

<!-- end generated -->

### `ssebench runs stop`

<!-- generated: cli runs stop -->

```sh
ssebench runs stop [-h] [--backend NAME] [--grace SECONDS] RUN_ID
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `RUN_ID` | *(required)* | The run's ID |
| `--grace SECONDS` | `20` | How long the entrypoint may take to clean up before the container is killed |

<!-- end generated -->

### `ssebench runs remove`

<!-- generated: cli runs remove -->

```sh
ssebench runs remove [-h] [--backend NAME] RUN_ID
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `RUN_ID` | *(required)* | The run's ID |

<!-- end generated -->

It removes the containers and volumes and leaves the run's `results/` directory
alone. It fails if the run is still there afterwards.

### `ssebench runs endpoint`

<!-- generated: cli runs endpoint -->

```sh
ssebench runs endpoint [-h] [--backend NAME] [--json] RUN_ID PORT
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `--json` | off | Print JSON instead of text |
| `RUN_ID` | *(required)* | The run's ID |
| `PORT` | *(required)* | A TCP port of the run's container |

<!-- end generated -->

With `--json` it prints `{"url": "http://host:port"}`. The URL is one that this
machine can use, whatever the backend: on Docker the container's address on its
network.

### `ssebench runs exec`

<!-- generated: cli runs exec -->

```sh
ssebench runs exec [-h] [--backend NAME] [--user USER] [--workdir DIR] [--tty] [--stdin]
                   [--env NAME]
                   RUN_ID COMMAND [COMMAND ...]
```

| Option | Default | Description |
|---|---|---|
| `--backend NAME` | docker, or `$SSEBENCH_BACKEND` | The runner backend; installed extensions can add more |
| `RUN_ID` | *(required)* | The run's ID |
| `--user USER` |  | Run as this user of the container |
| `--workdir DIR` |  | Working directory in the container |
| `--tty` | off | Allocate a terminal |
| `--stdin` | off | Keep standard input open |
| `--env NAME` | `[]` | Pass the variable NAME with the value it has here (repeatable); the value never appears in a command line |
| `COMMAND` | *(required)* | The command and its arguments |

<!-- end generated -->

```sh
uv run ssebench runs exec 20260929-153012-a1b2c3 --tty -- bash
```

A backend that cannot run commands in a run exits with status 1.

### `ssebench runs results`

<!-- generated: cli runs results -->

```sh
ssebench runs results [-h] [--json] [--dir DIR]
```

| Option | Default | Description |
|---|---|---|
| `--json` | off | Print JSON instead of text |
| `--dir DIR` | results in the working directory | The results directory |

<!-- end generated -->

It reads the `summary.json` of every run directory under the results directory,
at any depth, and needs no backend and no container. `--json` prints
`{"runs": [...]}`, newest first, each with `run_id`, `task`, `model`, `agent`,
`mode`, `reference_run`, `status` (the grade's), `started_at` and `dir`, the
run directory. Directories without a `summary.json`, such as a run in progress,
and summaries that do not parse are left out.

## `ssebench build-case`

Builds the case images of a dataset without running anything. Each image is
built for the platform that a run of its task uses, and the command warns once
when that is emulated; see
[Architectures](/deployment/host#architectures).

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

Writes the JSON Schemas of the task config, `dataset.yaml`, the manifest and the images lock,
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

### `ssebench dataset lock`

Writes the dataset's `images.lock.json`, which pins the published case image of
each task by digest, so that `ssebench run` [pulls exactly that image](#case-images).
The output keeps the images of the current lock whose task files are unchanged,
adds the ones in `--records`, and depends on nothing else. A dataset with no
published images has a lock with no images. `--check` fails when the file is
missing, is for another dataset version or pins a task the dataset does not
have; a lock that lags behind a changed task passes.

<!-- generated: cli dataset lock -->

```sh
ssebench dataset lock [-h] [--records DIR] [-o FILE] [--check] [DIR]
```

| Option | Default | Description |
|---|---|---|
| `DIR` | `datasets/pilot` in the SSEBench home | Dataset directory |
| `--records DIR` | none; keep the current images | Directory of publication records to add |
| `-o, --output FILE` | the images lock in the dataset | Output file |
| `--check` | off | Fail if the dataset's lock is missing, is for another version or names other tasks; write nothing |

<!-- end generated -->

### `ssebench dataset publish`

Pushes the case images of verified tasks to a registry and records the digests.
It publishes the image that `ssebench dataset verify` graded and no other: a
task with no result, a task that did not pass, and an image that was rebuilt
after the verification are refused. Log in to the registry first. The
[Dataset](https://github.com/42-b3yond-6ug/ssebench/blob/main/.github/workflows/dataset.yml)
workflow runs it for every task that passes, on a release tag and on a manual
run that asks for it, and never from a private repository.

```sh
uv run ssebench dataset verify gjson-196-bf4efcb
uv run ssebench dataset publish --registry ghcr.io/owner/repo gjson-196-bf4efcb
```

<!-- generated: cli dataset publish -->

```sh
ssebench dataset publish [-h] [--dir DIR] [-o OUTPUT] --registry PREFIX
                         [--revision COMMIT]
                         [TASK ...]
```

| Option | Default | Description |
|---|---|---|
| `TASK` | every task with a result | Tasks to publish |
| `--dir DIR` | `datasets/pilot` in the SSEBench home | Dataset directory |
| `-o, --output OUTPUT` | `results/dataset-verify` | Verification output |
| `--registry PREFIX` | *(required)* | Registry prefix, such as `ghcr.io/owner/repo` |
| `--revision COMMIT` | HEAD of the repository that holds the dataset | Full commit of the SSEBench repository that the dataset is at |

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
log of every run in `logs/`, the run directories, one for each attempt, in
`runs/results/`, and
`summary.md` and `summary.json`, a table of every task result in the directory
by check. It exits 1 when a task does not grade as expected. The
[Dataset](https://github.com/42-b3yond-6ug/ssebench/blob/main/.github/workflows/dataset.yml)
workflow runs it for all of them every week and for each release; before review,
run it for the tasks a branch changed with `--changed-since origin/main`
(`just verify dataset`).

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
ssebench proxy [-h] [--volumes] [--rebuild] ACTION
```

| Option | Default | Description |
|---|---|---|
| `ACTION` | *(required)* | up: build the proxy image if it is missing or older than `models/`, start the stack and wait until the proxy is healthy; build: only build the image, if it is missing or older than `models/`; down: stop the stack and keep its database volume |
| `--volumes` | off | With down, also remove the database volume: the next start creates a new database with the `POSTGRES_PASSWORD` of .env, and the proxy's stored keys and spend records are gone |
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

Starts, and removes, the [local demo](/getting-started/try#run-the-demo): the LiteLLM proxy
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
ssebench doctor [-h] [--json] [--verify-keys]
```

| Option | Default | Description |
|---|---|---|
| `--json` | off | Print the checks as JSON, with the provider keys that each model in `models/` needs and .env lacks |
| `--verify-keys` | off | Also send each provider key in .env to its provider's model-list endpoint, which is not billed, to see whether the provider accepts it; needs internet access |

<!-- end generated -->

It checks Docker, buildx and Compose, the free disk space where Docker keeps
its images, the CPU architecture (a warning on a host that is not amd64, where
every pilot task runs under emulation),
`.env` and the proxy secrets in it, whether the LiteLLM proxy answers on its
port, and which provider keys that `models/*.yaml` refers to are set. It exits
with status 1 when a required check fails; warnings do not change the exit
status.

Doctor contacts no provider unless you pass `--verify-keys`, which sends each key that
`.env` sets for Anthropic, OpenAI or Google to the provider's model-list
endpoint (`GET /v1/models`, or `/v1beta/models` for Google), which lists the
models the key may use and is not billed. A provider that rejects the key is a
warning: every model call with that key fails, and the run ends with status
`error` instead of a grade.

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
- the pilot manifest, `datasets/pilot/manifest.json`, and the digests of its
  published case images, `datasets/pilot/images.lock.json`, but not the task
  folders.

What a run needs beyond that comes from the registry and the network:

- The task's **case image** is [pulled](#case-images) from
  `$SSEBENCH_REGISTRY/case/<dataset>/<task>`, by the digest in the packaged
  `images.lock.json` when it pins the task. Without a task folder to build it
  from, a failed pull ends the run.
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

