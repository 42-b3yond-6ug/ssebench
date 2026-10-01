---
outline: deep
---

# Tasks and datasets

A **task** is one publicly disclosed vulnerability in an open-source project,
packaged so that an agent can try to fix it and a grader can check the fix. A
**dataset** is a versioned set of tasks, such as [pilot](/dataset/pilot), which
ships with SSEBench.

This page explains what a task is made of and how it reaches a run. The
[Dataset manifest](/dataset/manifest) page is the reference for the exact
layout, every key of the task config and the manifest format.

## What a task contains

A task is a folder named after its task ID, for example
`datasets/pilot/gjson-196-bf4efcb/`. It has two parts:

- a `Dockerfile` that builds the **case image**: the project's source at the
  vulnerable commit, its build dependencies, and the task's own files;
- an `sse/` directory with those task files, which the Dockerfile copies to
  `/ssebench` in the image.

```
<task-id>/
├── Dockerfile              case image: the project at the vulnerable commit
└── sse/                    copied to /ssebench in the image
    ├── config.yaml         the task config
    ├── build.sh            builds the project
    ├── run.sh              runs one proof of concept
    ├── test.sh             runs the project's tests
    ├── reports/            what the agent is told
    ├── pocs/               proof-of-concept inputs
    └── diffs/              the upstream fix and the hidden tests
```

The config, `sse/config.yaml`, ties these together. It names the project, its
language, the absolute path of the source tree in the image (`source`, for
example `/src/gjson`), what the agent is told (`task_description`), the scripts
(`scripts`) and the reference material (`files`). It also records where the
bug came from: the vulnerable and fixing upstream commits and links to the
advisory. `bench/src/ssebench/tasks/metadata.py` defines it, and
`ssebench dataset validate` rejects unknown keys.

## What the agent sees and what it doesn't

A task splits into material the agent works with and material only the grader
uses.

| The agent gets | The agent never gets |
|---|---|
| The project's source tree at `source`, owned by the agent's user, with the git history replaced by a single commit | The upstream fix (`files.patch`) and the upstream history |
| A [prompt](/concepts/prompt) built from the project's name and language, every field of `task_description`, the path of the source tree, and the build and test scripts | The hidden tests (`files.future_test`) |
| The `test_patch` tool, which runs the checks its [difficulty level](/concepts/difficulty-levels) allows | The proof-of-concept inputs, and any check its difficulty level withholds |

The bundled agents build their prompt with `sse.prompt.task_prompt()` from the
[Python SDK](/reference/python-sdk); see [Task prompt](/concepts/prompt).
Everything under `/ssebench` is readable by root only, so the agent reads the
report through its prompt and runs checks through `test_patch`; see the
[integrity model](/concepts/integrity).

## The checks a task defines

The scripts and files in the config decide which checks exist for the task.
The [grader](/concepts/grading) runs every one of them after the agent stops.

| Check | Needs | Passes when |
|---|---|---|
| `build` | `scripts.build` | The build script exits 0 on the patched project. |
| `poc` | `scripts.run` and `files.poc` | `run.sh <poc>` exits 0 for a proof of concept, meaning the vulnerability no longer triggers. |
| `function_test` | `scripts.test` | The project's existing tests pass. |
| `intent_test` | `scripts.test` and `files.future_test` | The tests pass after the hidden tests from the upstream fix are applied. |

Each task's `run.sh` decides what "the vulnerability triggers" means for its
project. The C tasks build with AddressSanitizer and fail when the output has a
sanitizer report or a segmentation fault; the Go tasks run the proof of concept
as a program and fail when it panics or exits non-zero; the Rust tasks build
and run a harness, kept in `/ssebench/harness`, that uses the project and
fails when the bug shows.

The manifest lists each task's checks in `tasks[].checks`. All 55 pilot tasks
have all four.

## Datasets

A dataset is a folder under `datasets/` with one folder per task, plus three
files:

- `dataset.yaml` holds the dataset version, such as `pilot-v1`. It changes
  whenever tasks are added, removed or changed in a way that can change their
  results. Dataset versions are separate from the SSEBench version; see
  [Releasing and versioning](/contributing/releasing).
- `manifest.json` lists every task with its language, project, images, checks,
  its validated config, and a SHA-256 checksum of every file in its folder.
  `ssebench dataset manifest` generates it, and `--check` fails when the
  committed file is out of date.
- `images.lock.json` pins the published case image of each task by digest, so
  that a run pulls exactly the image its release was published with. See the
  [images lock](/dataset/manifest#images-lock).

The JSON Schemas of the task config, `dataset.yaml`, the manifest and the images
lock are in `datasets/schema/`, exported from the Pydantic models by
`ssebench dataset schema`.

## Where a run gets its task

`ssebench run` gets a task in one of two ways:

```
--local datasets/pilot              --catalog <manifest, dir or URL>
        |                                    |   (default: the bundled pilot manifest)
        v                                    v
task folder on disk                 task entry in a manifest
        |                                    |
        | docker build in the folder         | docker pull $SSEBENCH_REGISTRY/case/<dataset>/<id>
        |                                    | by digest or by version tag (or, with
        |                                    | --build or when the pull fails, build
        |                                    | from a matching local folder)
        v                                    v
        +---------> case image <-------------+
```

- **From a dataset folder** (`--local DIR`). The CLI reads the task folder and
  builds the case image from its Dockerfile, as
  `$SSEBENCH_REGISTRY/case/<dataset>/<task-id>` in lowercase. `just run` uses
  `--local datasets/pilot` unless you pass `--local` or `--catalog` or set
  `SSEBENCH_CATALOG`.
- **From a catalog** (the default without `--local`). The CLI reads a
  manifest from a file, a directory or a URL, finds the task in it and pulls
  the [prebuilt case image](/dataset/pilot#prebuilt-images) from
  `$SSEBENCH_REGISTRY`, by the digest in the dataset's images lock when it has
  one, and otherwise by the dataset version tag. When the pull fails, or with
  `--build`, it builds the image from a local copy of the task folder whose
  checksums match the manifest, if there is one.

`ssebench tasks list` prints the tasks of a catalog, and
`ssebench tasks list --local DIR` those of a dataset folder. See
[Task catalog](/reference/cli#task-catalog) and the
[catalog service](/dataset/manifest#catalog-service).

The task ID is also the name of the results directory, `results/<task-id>/`;
see [Results format](/concepts/results).

## Next steps

- [Image layers](/concepts/image-layers): how the case image becomes the image
  a run uses
- [Grading pipeline](/concepts/grading): how the checks are run and recorded
- [Dataset manifest](/dataset/manifest): the task config and manifest in full
- [Add a task](/guides/add-a-task)
