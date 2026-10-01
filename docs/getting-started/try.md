---
outline: deep
---

# Try SSEBench without installing

You do not need the repository to try SSEBench. The `ssebench` command is on
PyPI, and [`uvx`](https://docs.astral.sh/uv/guides/tools/) runs it without
installing anything. The package carries the agent definitions, the model list
and the pilot task list, and the task images come from the registry.

This page runs the demo, an agent working on a task with your model key that you
watch in the web UI, then a task from the command line. To
change SSEBench, add tasks or agents, or use the `just` recipes, see
[Quickstart](/getting-started/quickstart).

## What you need

- A **Linux** host with **Docker Engine** and its buildx and Compose plugins.
  An x86-64 host is recommended, because every pilot task builds an amd64
  image. macOS with Docker Desktop is untested; see
  [macOS and Docker Desktop](/deployment/host#macos-and-docker-desktop).
- [**uv**](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- About **5 GB** of free disk for images, and network access.
- The API key of a model provider: Anthropic, OpenAI or Google. Without one,
  you can still run the demo with an agent that calls no model.

[Prerequisites](/getting-started/quickstart#prerequisites) shows how
to install Docker with its plugins on each system.

## Run the demo

In an empty directory, set up a workspace:

```sh
mkdir ssebench-work && cd ssebench-work
uvx ssebench init
```

`init` writes `.env` with generated local secrets, a copy of the model
definitions in `models/` and an empty `results/`. Run every `ssebench` command
from this directory.

Add the key of your model provider to `.env`:

```sh
ANTHROPIC_API_KEY=sk-ant-...    # or OPENAI_API_KEY, GOOGLE_API_KEY
```

To reach these providers through a router or gateway, see
[A compatible endpoint for the bundled providers](/guides/add-a-model#a-compatible-endpoint-for-the-bundled-providers).
Then start the demo with an agent and a model:

```sh
uvx ssebench demo up --agent claude-code --model claude-sonnet-4-6
```

The run calls the model with your key and **costs money**. The model names are
in `models/*.yaml`. `demo up` prints what it does:

1. **Checks the host** with the same checks as `ssebench doctor`, and that
   `.env` has the model's key. It stops before it builds anything when the key
   is missing, and says which one.
2. **Pulls the images** of the task catalog, the web UI and the task, at the
   version of the package. The LiteLLM proxy image is built from `models/`, on
   top of the published LiteLLM image.
3. **Starts the stack** as the Compose project `ssebench-demo`: the
   [LiteLLM proxy](/concepts/litellm-proxy) with its Postgres database, the task
   catalog and the [web UI](/webui/).
4. **Runs the agent** on `gjson-196-bf4efcb`, a Go task that builds in seconds.
   It prints the address of the web UI, `http://127.0.0.1:3001`, before the run
   starts, so you can watch the agent live. The agent stops after `--timeout`
   seconds (one hour by default).
5. **Prints the result** when the evaluator has graded the run.

The first time, the images take a few minutes; see
[How long it takes](#how-long-it-takes).

### Without a key

Without `--agent`, the demo runs the
[`reference`](/reference/cli#reference-runs) agent, which applies the task's
known upstream fix instead of asking a model for one. It needs **no model and
no key**, and every check passes:

```sh
uvx ssebench demo up
```

```text
Done in 41s (images 0s, stack 15s, run 26s).
Result:  build passed, PoC 1/1 passed, functional tests passed, intent tests passed

Open http://127.0.0.1:3001
The run gjson-196-bf4efcb / reference is listed there, with its dialog, diff and evaluation result.
```

### Look at the run

Open `http://127.0.0.1:3001` and click the run in the list on the left. The web
UI lists every SSEBench container of the Docker daemon it talks to, so on a
machine that also runs other benchmarks you will see those runs too.

- **Agent Dialog** (left) is what the agent did: its messages and tool calls.
  The reference agent only applies the patch and finishes.
- **Changes** shows the diff of the source tree against the vulnerable commit.
- **Evaluation Result**, a card at the end of the dialog, shows the grade: the build, the functional tests, the
  proof-of-concept check (**Security**) and the tests that came with the
  upstream fix (**Intent**). A reference run is marked as one.

[Watching a run](/webui/run-view) explains each panel. The same data is
available from the API:

```sh
curl -s http://127.0.0.1:3001/api/containers      # the runs
curl -s http://127.0.0.1:3001/api/containers/<id>/result
```

### Demo options

| Option | What it does |
|---|---|
| `--task ID` | Run another pilot task; `uvx ssebench tasks list` shows them. Choose one that builds quickly; C tasks take longer. |
| `--agent NAME`, `--model NAME` | The agent and its model. `--model` is optional for `reference` only. |
| `--timeout SECONDS` | How long the agent may run. |

`demo up` again replaces the earlier run in the web UI. The
[CLI reference](/reference/cli#ssebench-demo) lists the options.

### Stop the demo

```sh
uvx ssebench demo down
```

This removes the demo's run containers, the `ssebench-demo` Compose project
and its database volume. It does not touch other containers, other Compose
projects, the cached images or `results/`, where the run's files stay.

A finished run keeps its container alive so that the web UI can show it, until
`demo down` or `docker rm -f` removes it. The web UI shows only such containers
today.

## Run a task from the command line

`ssebench run` runs one agent on one task, grades the result and exits, with no
web UI. From your workspace, with your key in `.env`:

```sh
uvx ssebench doctor
uvx ssebench tasks list
uvx ssebench run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

`doctor` checks Docker, disk space and `.env`, and its `Provider keys` line
names the keys that are set; [Troubleshooting](/getting-started/troubleshooting)
explains each check. `tasks list` prints the 55 pilot tasks.

A real agent works until it stops or reaches the timeout (one hour by default,
`--timeout` changes it), so start with a small task like this one.
`ssebench run` starts the LiteLLM proxy if it is not running, pulls the task's
[case image](/dataset/pilot#prebuilt-images), builds the tool and agent
[image layers](/concepts/image-layers) on top of it, runs the agent and grades
what it left behind. The proxy reads provider keys from `.env` only, not from
your shell. Edit `models/` to add or change a model; `ssebench run` rebuilds
the proxy image when a file changes. `--difficulty` sets how much the agent may
check while it works; see [Difficulty levels](/concepts/difficulty-levels).

::: tip Without a key
`uvx ssebench run --task gjson-196-bf4efcb --agent reference` applies the
task's known fix and passes, with no model and no key.
`--agent dummy --model claude-sonnet-4-6` makes no model calls either: it
changes nothing, so the patch fails. That is expected, and it shows that your
images, proxy and grading work.
:::

`uv tool install ssebench` keeps the command on your `PATH` as `ssebench`
instead of running it through `uvx`. [CLI](/reference/cli#without-a-clone)
describes what the package carries and what it pulls.

## Read the results

Every run writes its own directory under `results/` in the workspace:

```text
results/
└── gjson-196-bf4efcb/none/reference/
    ├── latest -> 20260929-153012-a1b2c3       the newest run
    └── 20260929-153012-a1b2c3/                the run directory: everything the container produced
        ├── summary.json                       the summary: the grade, the settings, the spend
        ├── result.json                        the grade
        ├── final.patch                        the patch that was graded
        ├── source.tar.gz                      the source tree after grading
        ├── agent.log  daemon.log  mcp.log  evaluator.log  …
        └── archive/dialog.jsonl               the agent's session
```

The run directory is `results/<task>/<model>/<agent>/<run-id>/`. A reference run
has the model `none`; the run of `claude-code` above writes
`results/gjson-196-bf4efcb/claude-sonnet-4-6/claude-code/<run-id>/`. The run ID
is the time in UTC and six random hex digits, or the `--run-id` you give.
Running the same combination again makes another directory, so repeated trials
keep their results.

`ssebench run` prints the grade and the path of the run directory when it ends.
`result.json` is the evaluator's grade; `latest` is the newest run:

```sh
jq .patch_result results/gjson-196-bf4efcb/none/reference/latest/result.json
```

```json
{
  "status": "passed",
  "build_success": true,
  "pov_passed": 1,
  "pov_total": 1,
  "func_test_success": true,
  "intent_test_success": true,
  "error_msg": null,
  "error_log": null
}
```

| Field | Meaning |
|---|---|
| `status` | `passed` when every check that ran passed, `failed` when a check failed or the patch did not apply, `error` when nothing could be graded. |
| `build_success` | The patched project builds. |
| `pov_passed`, `pov_total` | How many of the task's proof-of-concept inputs no longer trigger the vulnerability. |
| `func_test_success` | The project's own tests pass. |
| `intent_test_success` | The tests that came with the upstream fix pass. |
| `error_msg`, `error_log` | The first check that failed, and its output. |

A check that did not run, because the task does not have it or an earlier
failure ended grading, is `null`. `runtime_result` records how long the agent ran
and whether it timed out. The summary adds the run settings as `config` and what
the model calls cost as `spend`, in US dollars. [Results format](/concepts/results)
describes every file, and [Grading pipeline](/concepts/grading) how to read a
grade.

::: tip A `failed` grade that came too quickly
When the agent never got to work, for example because its provider key is missing
or invalid, the run still ends with a grade: `failed`, with the proof of concept
of the untouched source tree as `error_msg`, and a `spend` of 0. Look at
`agent.log` in the run directory, and see [Troubleshooting](/getting-started/troubleshooting#the-agent-ended-at-once-or-said-it-could-not-log-in).
:::

A demo run's container is still alive for the web UI, so its `result.json` has
no `config` yet, and the summary is not written, until `demo down` removes the
container.

## How long it takes

Measured on a 48-core host with a fast connection:

| | Time | What happens |
|---|---|---|
| Warm | 26 s (41 s from a stopped stack) | Every image is cached. |
| First run | about 2 min (estimated) | Downloads of about 1.1 GB compressed (LiteLLM 390 MB, Postgres 160 MB, the case image 240 MB, the web UI 95 MB, small images and Python packages for the rest), then the tool and agent layers, which take 10 s with the published runtime image. |

The first run is estimated from the image sizes and the rate of a pull on this
host (23 MB/s). Downloads scale with the connection: on a small VM with 2 vCPUs
and 100 Mbit/s, expect four to six minutes, most of it downloads and the
LiteLLM proxy's start.

## Settings

Set them in the shell, or in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `SSEBENCH_DEMO_WEBUI_PORT` | `3001` | Port of the web UI on `127.0.0.1`. |
| `SSEBENCH_DEMO_CATALOG_PORT` | `8090` | Port of the catalog service on `127.0.0.1`. |
| `LITELLM_PORT` | `4000` | Port of the LiteLLM proxy. |
| `SSEBENCH_DEMO_PROJECT` | `ssebench-demo` | Compose project of the demo. Give it a name of its own: `demo down` deletes the project's volume. |
| `SSEBENCH_WEBUI_TERMINAL` | `0` in the demo | `1` turns on the terminal into the run container. |

The demo stops early, and names the variable, when a port is taken. It can run
next to the stack of `ssebench proxy up`, which is a different Compose project,
when their ports differ: `LITELLM_PORT=4001 uvx ssebench demo up`.

## When the demo fails

- **A port is in use.** Set the variable named in the message.
- **`fail Disk`, `fail Docker` and other failed checks.** The message under the
  check says how to fix it; `ssebench doctor` shows the same checks.
- **The run failed.** The demo prints the end of the run's log, and its path
  under `results/`. The stack keeps running, so you can look at it, and
  `demo down` removes it.
- **The web UI does not list the run, or says the Docker daemon is not
  reachable.** The web UI container mounts `/var/run/docker.sock`, so the
  daemon's socket has to be there, and the engine has to run containers on the
  host's network namespace. On Docker Desktop, that means turning on **Enable
  host networking** (4.34 or later) and restarting it; see
  [macOS and Docker Desktop](/deployment/host#macos-and-docker-desktop).
  The run itself and `results/` do not depend on the web UI.
- **A pull fails with `denied` or `not found`.** The registry does not have the
  images of this version. The package has nothing to build them from, so run
  the demo [from a clone](/getting-started/quickstart#run-the-demo), which
  builds them.

[Troubleshooting](/getting-started/troubleshooting) covers the rest.

## Security

The web UI can stop and remove SSEBench containers and read their logs and
files, so it is bound to `127.0.0.1` and, in the demo, has no terminal. It
runs as a container that has the Docker socket, which is root access to the
host: run the demo on a machine you control, and see
[Web UI security](/webui/security). The catalog listens on `127.0.0.1` as well.
The LiteLLM proxy listens on `127.0.0.1` at `LITELLM_PORT` (`LITELLM_BIND` sets
another address), and asks for the master key from `.env` for everything but its
health check.

## Next steps

- [Quickstart](/getting-started/quickstart): clone the repository
  to change SSEBench, add tasks and agents, and use the `just` recipes
- [Web UI](/webui/): launch runs and watch them live
- [Architecture](/concepts/architecture): what happens during a run
- [Add a model](/guides/add-a-model): use another provider or model
- [The pilot dataset](/dataset/pilot): the tasks you can run
