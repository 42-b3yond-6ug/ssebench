---
outline: deep
---

# Add a task

A task is one publicly disclosed vulnerability in an open-source project,
packaged so that an agent can try to fix it and the grader can check the fix.
This guide adds one to a dataset, using `pilot` in `datasets/pilot/`. Read
[Tasks and datasets](/concepts/tasks-and-datasets) for the concepts, and keep
[Dataset manifest](/dataset/manifest) at hand: it is the reference for the
layout and every key of the config, which this guide does not repeat.

## Before you start

A task needs:

- a **publicly disclosed vulnerability** with an advisory or an issue, and an
  **upstream fix** you can name by commit. Do not add a problem that is not
  fixed or disclosed upstream; report that privately, as
  [SECURITY.md](https://github.com/42-b3yond-6ug/ssebench/blob/main/SECURITY.md)
  describes;
- a **language** that has a base image: C, Go or Rust (`images/base-images/`);
- a **reproducer** that triggers the bug on the vulnerable commit, from the
  report, or one you write;
- **project tests** that pass on the vulnerable commit, without the network;
- an **open-source license** for the upstream project, which you record for
  the task (see [Record the upstream project](#record-the-upstream-project)).

You also need Docker with buildx and a checkout on which `just setup` has run;
see [Contributing](/contributing/). Material you write for a task is licensed
under CC BY 4.0, and the upstream code, fixes and tests in it keep their own
licenses; `datasets/pilot/THIRD_PARTY.md` lists them.

## The task folder

A task is a folder named after its **task ID**. IDs are letters and digits
separated by `.`, `_` or `-`. The ID is a command-line argument, an image name
(`case/<dataset>/<id>` in lowercase) and a results path, so keep it short and
make it identify the bug. The pilot tasks use the project, the number of the
issue and the short hash of the fix (`gjson-196-bf4efcb`), or an advisory ID
(`RUSTSEC-2019-0009`).

```
datasets/pilot/<task-id>/
├── Dockerfile              builds the case image
├── README.md               optional notes; how to reproduce by hand
└── sse/                    copied to /ssebench in the image
    ├── config.yaml         describes the task
    ├── build.sh            builds the project
    ├── run.sh              runs one proof of concept
    ├── test.sh             runs the project's tests
    ├── pocs/               proof-of-concept inputs
    ├── reports/            what the agent is told
    └── diffs/              the upstream fix and the hidden tests
```

The quickest way to start is to copy a task in the same language and change
what differs:

```sh
cp -r datasets/pilot/gjson-196-bf4efcb datasets/pilot/<task-id>
```

Set `id` in `sse/config.yaml` to the new folder name, then work through the
sections below. A task folder may hold more build inputs beside `sse/`: the
Rust tasks keep a vendored crate, a harness and a `Cargo.lock` there.

## The Dockerfile

The Dockerfile builds the **case image**: the project at the vulnerable commit,
everything needed to build and test it without a network, and the task files.
Its rules are checked by `ssebench dataset validate`, and the example is
`gjson-196-bf4efcb/Dockerfile`:

```dockerfile
ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:1.0.0

WORKDIR /src/gjson

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

ENV GOFLAGS="-mod=vendor"

RUN git clone https://github.com/tidwall/gjson.git /src/gjson && \
    cd /src/gjson && \
    git checkout 9f58baa7a613f89dfdc764c39e47fd3a15606153 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && echo "/vendor/" >> .gitignore && git add --all && git commit -m "buggy commit" && \
    go mod download && \
    go mod vendor && \
    go mod verify

COPY sse/config.yaml /ssebench/config.yaml
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports

RUN cd /ssebench/pocs && \
    go mod init poc-gjson && \
    go mod edit -replace github.com/tidwall/gjson=/src/gjson && \
    go mod tidy

RUN chmod +x /ssebench/scripts/*.sh
```

- **Declare `ARG SSEBENCH_REGISTRY` before the first `FROM`, and end on
  `FROM ${SSEBENCH_REGISTRY}/base-generic-<lang>:<version>`.** The CLI builds
  with `--build-arg SSEBENCH_REGISTRY=…`, which lets you build against a local
  registry. The base needs a version tag or a digest, not `latest`: every
  pilot task uses `1.0.0`. See
  [Base images](/dataset/manifest#base-images).
- **Pin what decides the result.** Check out a full 40-character commit, not a
  branch or tag. Pin a toolchain when the task needs a specific one (a Rust
  task calls `rustup default nightly-2022-07-11`), and commit a lockfile when
  upstream has none (`Cargo.lock` next to the Dockerfile).
- **Start from one commit.** Delete upstream's `.git` and commit the tree as
  `buggy commit`, as the pilot tasks do, so that the fix is not in the image's
  history. The tool layer does the same for the agent's copy, and keeps the
  case image's checkout as the copy that grading applies the agent's patch to.
- **Fetch every dependency at build time.** Grading runs without a network:
  under the default egress policy the run container reaches only the LiteLLM
  proxy, so `build.sh`, `run.sh` and `test.sh`, with or without the fix and the
  hidden tests applied, must find their packages, modules, crates, toolchains
  and test data in the image. Go tasks run `go mod vendor` and set
  `GOFLAGS=-mod=vendor`; Rust tasks run `cargo fetch`.
- **Copy `sse/` to `/ssebench`**, with `sse/config.yaml` at
  `/ssebench/config.yaml`. Every path in the config is relative to `/ssebench`
  and must be a file that the Dockerfile copies from the task folder.
- **Make the scripts executable** with `chmod +x`. The daemon runs them
  directly.

## The config

`sse/config.yaml` describes the task to the CLI, the daemon and the grader.
Unknown keys are rejected. A Go task:

```yaml
id: gjson-196-bf4efcb
project: gjson
repository: https://github.com/tidwall/gjson
language: go
source: /src/gjson
task_description:
  crash_report:
  - reports/crash_report_1.txt
  - reports/issue.md
scripts:
  build: scripts/build.sh
  run: scripts/run.sh
  test: scripts/test.sh
files:
  patch: diffs/patch.diff
  poc:
  - pocs/poc.go
  future_test: diffs/test.diff
type: Slice bounds out of range
trigger_commit: 9f58baa7a613f89dfdc764c39e47fd3a15606153
patch_commit: bf4efcb3c18d1825b2988603dea5909140a5302b
reference:
- https://github.com/tidwall/gjson/issues/196
- https://github.com/tidwall/gjson/commit/bf4efcb3c18d1825b2988603dea5909140a5302b
originality: public
```

The reference is [Task config](/dataset/manifest#task-config) and, for the
generated key list, [Configuration files](/reference/configuration#sse-config-yaml);
`datasets/schema/task.schema.json` is the JSON Schema. What matters when you
write one:

- `source` is the absolute path of the project's tree in the case image. The
  agent edits it, and the scripts run on copies of it.
- Which checks a task has follows from the config: a `build` script gives a
  build check; `run` and `poc` give the proof-of-concept check; `test` gives
  the functional tests; `test` and `future_test` give the intent tests. A task
  without one of these simply has no such check.
- `task_description` needs at least one of `issue`, `crash_report` and
  `bug_description`. The prompt of the bundled agents shows every one that is
  set, with the contents of the report files listed under `crash_report`; see
  [Task prompt](/concepts/prompt). Put the text the agent should read in
  `reports/` and list the files there.
- `patch_commit` and `reference` are for people: the agent does not see them.
  The upstream fix (`files.patch`) and the hidden tests (`files.future_test`)
  never reach the agent either. `security_test` and `intent_test` under
  `files` are not used by the grader.
- `originality` is `public` when the proofs of concept come from the public
  report, and `crafted` when you wrote them; it should agree with the
  provenance you record in `third_party.json` (`written` for `crafted`).

## The scripts

The daemon runs the task's scripts for the agent's `test_patch` tool and for
grading, and each script's exit status is the verdict. This is what they can
count on, checked against a run:

| | `build.sh` | `run.sh` | `test.sh` |
|---|---|---|---|
| Called as | `build.sh` | `run.sh <poc>`, one absolute path, `/ssebench/pocs/…`, for each file in `files.poc` | `test.sh` |
| Exit 0 means | the project built | the proof of concept **no longer triggers** the bug | the project's tests pass |
| Working directory | a fresh temporary copy of the source tree (`/tmp/.tmp…`) | the copy the last `build.sh` left behind | a fresh temporary copy |
| Runs as | root | root | root |

Also:

- Each script starts with a shebang and runs directly from
  `/ssebench/scripts/`, with the environment the image sets (`ENV`) and
  `HOME=/root`. Under the default egress policy it has no network.
- `test.sh` starts from a copy that nobody has built, so it builds first, as
  gjson's does with `/ssebench/scripts/build.sh`. The agent's prompt shows the
  text of the build and test scripts, with that line replaced by a comment, so
  they must not say anything that gives the answer away.
- Refer to the project through the working directory. The scripts run on
  copies, so a check that names the source by its absolute path tests the tree
  at that path, not the copy it was meant to check. gjson's proof of concept
  is an example to avoid: its `go.mod` replaces the module with `/src/gjson`.
- The evaluator grades under the same time limit as the agent (`TIMEOUT`, 3600
  seconds by default), and a run executes `test.sh` more than once, for
  `test_patch` and for each test check of grading. Keep the scripts fast and
  deterministic.

### How a proof of concept is judged

`run.sh` decides what triggering the vulnerability means for the project, and
reports it as the exit status: non-zero while the bug triggers, zero once it
does not. The pilot tasks show three ways:

- **C** tasks build with AddressSanitizer in `build.sh`, and `run.sh` feeds the
  input to the program and exits 1 if the output has a sanitizer report or a
  segmentation fault;
- **Go** tasks make the proof of concept a program that uses the project, and
  `run.sh` runs it (`go run`) and returns its exit status: a panic is non-zero;
- **Rust** tasks build a harness, kept in `/ssebench/harness`, and run it.

A proof of concept that fails for another reason, such as a compile error, also
exits non-zero and so counts as still triggering. A patch that makes the project
reject the input passes; whether it keeps the project working is what the
tests are for. See [How a proof of concept is judged](/concepts/grading#how-a-proof-of-concept-is-judged).

## The diffs

`sse/diffs/` holds two unified diffs, in the `git diff` format with the `a/`
and `b/` prefixes, relative to the source directory:

- `patch.diff` is the **upstream fix**: only the change to the project, not its
  tests. It is what the `reference` agent applies, with `git apply -p1`, and
  it is never shown to the agent.
- `test.diff`, named by `files.future_test`, holds the **hidden tests**: usually
  the tests that the upstream fix added or changed. The intent test applies it
  to a copy of the agent's patched tree with `git apply -p1` and runs
  `test.sh`. A diff that does not apply, because the agent's patch changed the
  lines around it, counts as a failed test. Keep it to test files, and choose
  tests that fail on the vulnerable code and pass with the upstream fix.

## The proofs of concept and the reports

- **`sse/pocs/`** holds the inputs that `run.sh` takes, listed under
  `files.poc`. A task without one has no proof-of-concept check. Whether they
  come from the report or you wrote them is recorded with `originality`.
- **`sse/reports/`** holds the text the agent reads: the issue, and a crash
  report or sanitizer log when there is one. The agent gets it verbatim, so
  strip anything that gives the fix away.

## Record the upstream project

Each task's upstream project, license, fix, advisories and where the proof of
concept came from are kept in `datasets/pilot/third_party.json`, and
`datasets/pilot/THIRD_PARTY.md` is generated from it and the task folders. Do
not edit `THIRD_PARTY.md`.

```json
"upstreams": {
  "https://github.com/tidwall/gjson": {
    "name": "GJSON",
    "license": "MIT",
    "license_files": ["LICENSE"]
  }
},
"tasks": {
  "gjson-196-bf4efcb": {
    "upstream": "https://github.com/tidwall/gjson",
    "report": "https://github.com/tidwall/gjson/issues/196",
    "advisories": ["CVE-2020-36067", "GHSA-p64j-r5f4-pwwx", "GO-2021-0054"],
    "pocs": [{"files": ["sse/pocs/poc.go"], "kind": "derived"}],
    "license_checked_at": "9f58baa7a613f89dfdc764c39e47fd3a15606153"
  }
}
```

- An **upstream** entry, added once per project, gives its `name`, an SPDX
  `license` expression and the `license_files` you read it from. A license the
  script does not know yet (`KNOWN_SPDX` in `tools/dataset/third_party.py`) is
  an error until you add it. A copyleft project also gets a `note`.
- A **task** entry names the `upstream`, the `report`, the `advisories`
  (`CVE-`, `GHSA-`, `GO-` or `RUSTSEC-` IDs, including every one the config's
  `reference` cites), the provenance of each proof-of-concept file (`kind` is
  `report`, `derived` or `written`, or free `text`), and
  `license_checked_at`, the commit at which you read the license: it must equal
  the commit the Dockerfile checks out. A task that vendors its source instead
  of cloning it has a `vendored` entry.

Then generate the file, and check it:

```sh
python3 tools/dataset/third_party.py            # rewrites THIRD_PARTY.md
python3 tools/dataset/third_party.py --check    # exits 1 if it is out of date
```

Without an entry, or when the Dockerfile and the entry disagree, it says what is
wrong: `error: <task-id>: missing from third_party.json`.

## Check the task

### 1. Validate the folder

```sh
uv run ssebench dataset validate datasets/pilot
```

It checks every task folder of the dataset against the rules above, without
building anything, and lists every problem per task. It exits 1 if any task is
invalid:

```text
my-task:
  sse/config.yaml: foo: unknown key
  Dockerfile: FROM uses SSEBENCH_REGISTRY, but no ARG SSEBENCH_REGISTRY precedes it
  Dockerfile: copies sse/tests.sh, which does not exist
datasets/pilot: 1 of <n> tasks are invalid
```

A valid dataset prints `datasets/pilot: <n> tasks are valid`.

### 2. Try the scripts by hand

Build the case image, then run the scripts in a container without a network,
the way grading will:

```sh
uv run ssebench build-case --benchmarks datasets/pilot --tasks <task-id> --force
image=${SSEBENCH_REGISTRY:-ghcr.io/42-b3yond-6ug/ssebench}/case/pilot/<task-id>   # in lowercase

docker run --rm --network none "$image" bash -c \
  'cd <source> && /ssebench/scripts/build.sh && /ssebench/scripts/test.sh'

docker run --rm --network none "$image" bash -c \
  'cd <source> && git apply -p1 /ssebench/diffs/patch.diff \
   && git apply -p1 /ssebench/diffs/test.diff \
   && /ssebench/scripts/test.sh && /ssebench/scripts/run.sh /ssebench/pocs/<poc>'
```

The first must pass, so the project builds and its tests pass on the
vulnerable commit. The second must pass too: with the fix and the hidden tests
applied, the tests pass and the proof of concept no longer triggers. Run
`run.sh` on the unfixed tree as well: it must fail. `<source>` is the `source`
path of the config. `ssebench build-case` skips an image that exists unless you
pass `--force`.

### 3. Run it with the `reference` and `dummy` agents

The two agents bracket a sound task. The `reference` agent applies
`files.patch` and needs no model; the `dummy` agent changes nothing:

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent reference
uv run ssebench run --local datasets/pilot --task <task-id> --agent dummy --model claude-sonnet-4-6

jq -c '.patch_result | del(.error_log)' results/<task-id>/none/reference/latest/result.json
jq -c '.patch_result | del(.error_log)' results/<task-id>/claude-sonnet-4-6/dummy/latest/result.json
```

For a sound task, such as a copy of `gjson-196-bf4efcb`, the two grades are:

```json
{"status":"passed","build_success":true,"pov_passed":1,"pov_total":1,"func_test_success":true,"intent_test_success":true,"error_msg":null}
{"status":"failed","build_success":true,"pov_passed":0,"pov_total":1,"func_test_success":true,"intent_test_success":false,"error_msg":"PoC failed: /ssebench/pocs/poc.go"}
```

| Agent | `status` | Build | Proofs of concept | Functional tests | Intent tests |
|---|---|---|---|---|---|
| `reference` | `passed` | pass | all pass | pass | pass |
| `dummy` | `failed` | pass | fail | pass | fail |

A `reference` run that fails a check means the task is unsound: the fix, the
scripts or the image are wrong. A `dummy` run that passes a check means that
check does not test the bug: the proof of concept does not trigger it, or the
hidden tests do not fail without the fix. The `reference` run is labelled as
such and never counts as a model's score; see
[Reference runs](/reference/cli#reference-runs).

`just dataset-verify` runs both agents and compares their grades with the table
above, for one task or several (`--jobs` sets how many run at once):

```sh
just dataset-verify <task-id>
```

It prints a table of task by check and lists every check that did not grade as
expected, with the log of each run under `results/dataset-verify/logs/`. See
[`ssebench dataset verify`](/reference/cli#ssebench-dataset-verify).

## Regenerate the manifest

`manifest.json` lists every task with the checksums of its files, so it changes
whenever anything in a task folder does. Regenerate it after your last edit:

```sh
uv run ssebench dataset manifest
uv run ssebench dataset manifest --check     # exits 1, with a diff, when it is stale
```

```text
wrote datasets/pilot/manifest.json with <n> tasks
datasets/pilot/manifest.json is up to date
```

The manifest records the dataset's version too. A new task changes the dataset,
so bump `version` in `datasets/pilot/dataset.yaml` first (see
[Dataset version](/dataset/manifest#dataset-version)), and update any text that
states how many tasks `pilot` has, such as [The pilot dataset](/dataset/pilot) and
the [dataset card](https://github.com/42-b3yond-6ug/ssebench/blob/main/datasets/pilot/README.md).

## Before you open the pull request

CI runs, for changes under `datasets/` and `tools/dataset/`:

```sh
uv run ssebench dataset validate datasets/pilot
uv run ssebench dataset manifest --check
uv run ssebench dataset schema --check
uv run python tools/dataset/third_party.py --check
```

The Dataset workflow then runs `ssebench dataset verify` for every task the
pull request changes. Run those checks and `just dataset-verify <task-id>`
yourself first, and read
[Contributing](https://github.com/42-b3yond-6ug/ssebench/blob/main/CONTRIBUTING.md)
for the rest of the process. Never include API keys, `.env` files or `results/`.

A short checklist:

- The ID is the folder name and the config's `id`.
- The Dockerfile declares `ARG SSEBENCH_REGISTRY`, ends on a pinned
  `base-generic-<lang>` image, pins the commit, and fetches everything at build
  time.
- `build.sh`, `run.sh` and `test.sh` work without a network and use the
  working directory, not the source's absolute path.
- The proof of concept fails before the fix and passes after it.
- The hidden tests fail before the fix and pass after it.
- `reference` passes every check, and `dummy` fails the proofs of concept and
  the intent tests.
- The reports do not give the fix away.
- `third_party.json` has the task, and `THIRD_PARTY.md` and `manifest.json` are
  regenerated.

## Next steps

- [Dataset manifest](/dataset/manifest): the layout, the config keys and the
  manifest format
- [Grading pipeline](/concepts/grading): how each check is run and recorded
- [Integrity model](/concepts/integrity): what the agent cannot see
- [Add an agent](/guides/add-an-agent)
