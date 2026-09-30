---
outline: deep
---

# Try the demo

`just demo` starts a local SSEBench stack, runs an agent on one pilot task and
leaves the finished run open in the [web UI](/webui/). By default the agent is
[`reference`](/reference/cli#reference-runs), which applies the task's known
upstream fix instead of asking a model for one, so the demo needs **no model
and no API key**. The grade checks the task and the grader: every check passes.

## Before you start

You need a Linux host with Docker (with the buildx and Compose plugins),
[uv](https://docs.astral.sh/uv/), [just](https://just.systems/) and a clone of
the repository; see [Installation](/getting-started/installation). The demo
does not need Bun, Rust or Go. It uses about 4 GB of disk for images, and about 11 GB more of build cache when the images are built from the checkout (see [Disk space](/getting-started/installation#prerequisites)). Docker
Desktop and other engines that run containers in a VM have not been tested,
because the web UI container uses the host's network to reach the run
containers.

## Run it

From the repository root:

```sh
just setup    # once: dependencies, and .env with generated local secrets
just demo
```

`just demo` prints what it does:

1. **Checks the host** with the same checks as `just doctor`.
2. **Gets the images.** It pulls the images of the catalog, the web UI, the
   runtime and the task at this checkout's version. The registry does not
   have an image before a release, so the demo builds it from this checkout
   instead; `--build` builds everything and pulls nothing. The LiteLLM proxy
   image is always built from `models/`, on top of the published LiteLLM image.
3. **Starts the stack** as the Compose project `ssebench-demo`: the LiteLLM
   proxy with its Postgres database, the task catalog serving the bundled pilot
   manifest, and the web UI.
4. **Runs the agent** on `gjson-196-bf4efcb`, a Go task that builds in seconds,
   and shows its progress.
5. **Prints the result and the address of the web UI:**

```text
Done in 41s (images 0s, stack 15s, run 26s).
Result:  build passed, PoC 1/1 passed, functional tests passed, intent tests passed

Open http://127.0.0.1:3001
The run gjson-196-bf4efcb / reference is listed there, with its dialog, diff and evaluation result.
```

The times depend on the host and on what Docker has cached; see
[How long it takes](#how-long-it-takes).

### Without a clone

The demo also runs from a [package install](/reference/cli#without-a-clone), where
there is no `just`:

```sh
uvx ssebench init          # once, in an empty directory
uvx ssebench demo up
uvx ssebench demo down
```

The images must be in the registry then, because a package install has nothing
to build the catalog, the web UI or the task from, so this works once the images
of the release are published.

## Look at the run

Open `http://127.0.0.1:3001` and click the run in the list on the left. The web
UI lists every SSEBench container of the Docker daemon it talks to, so on a
machine that also runs other benchmarks you will see those runs too.

- **Agent Dialog** (left) is what the agent did. The reference agent applies
  the patch and finishes; other agents show their messages and tool calls.
- **Changes** shows the diff of the source tree against the vulnerable commit.
- **Evaluation Result** shows the grade: the build, the functional tests, the
  proof-of-concept check (**Security**) and the tests that came with the
  upstream fix (**Intent**). A reference run is marked as one.

The same data is available from the API:

```sh
curl -s http://127.0.0.1:3001/api/containers      # the runs
curl -s http://127.0.0.1:3001/api/containers/<id>/result
```

## Use your own key

To see a real agent work, put the key of your model provider in `.env`
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GOOGLE_API_KEY`) and name the agent
and the model:

```sh
just demo --agent claude-code --model claude-sonnet-4-6
```

The demo stops before it builds anything when the model's key is missing from
`.env`, and says which one. The model names are in `models/*.yaml`. The run
calls the model with your key and **costs money**. The demo prints the address
of the web UI before the run starts, so you can watch it live, and the agent
stops after `--timeout` seconds (one hour by default). Other options:

| Option | What it does |
|---|---|
| `--task ID` | Run another task of the pilot dataset; `uv run ssebench tasks list` shows them. Choose one that builds quickly; C tasks take longer. |
| `--agent NAME`, `--model NAME` | The agent, a directory under `agents/`, and its model. `--model` is optional for `reference` only. |
| `--timeout SECONDS` | How long the agent may run. |
| `--build` | Build every image from this checkout instead of pulling. |

`just demo` again replaces the earlier run in the web UI. The
[CLI reference](/reference/cli#ssebench-demo) lists the options.

## Stop it

```sh
just demo-down
```

This removes the demo's run containers, the `ssebench-demo` Compose project
and its database volume. It does not touch other containers, other Compose
projects (not even the stack of `just launch`), the cached images or
`results/`, where the run's files stay.

A finished run keeps its container alive so that the web UI can show it, until
`just demo-down` or `docker rm -f` removes it. The web UI shows only such
containers today.

## How long it takes

Measured on a 48-core host with a fast connection:

| | Time | What happens |
|---|---|---|
| Warm | 26 s (41 s from a stopped stack) | Every image is cached. |
| Images pulled | about 2 min (estimated) | Downloads of about 1.1 GB compressed (LiteLLM 390 MB, Postgres 160 MB, the case image 240 MB, the web UI 95 MB, small images and Python packages for the rest), then the tool and agent layers, which take 10 s with the published runtime image. |
| Images built from the checkout (`--build`, before a release), cold | 3 to 4 min (3 min 15 s measured on a fresh machine, with no cached image or build) | The images take about 30 s: the LiteLLM proxy, the catalog, the web UI and the base image, plus the download of Postgres. The stack takes 20 s. The run takes about 2 min, almost all of it building the tool layer, because the daemon compiles. |

The pulled path is estimated from the image sizes and the rate of a pull on
this host (23 MB/s). Builds and the daemon's compile scale with the number of
cores, and downloads with the connection: on a small VM with 2 vCPUs and 100 Mbit/s, expect the pulled path to
take four to six minutes, most of it downloads and the LiteLLM proxy's start,
and the build from a checkout several times longer than on the large host
(estimated).

## Settings

Set them in the shell, or in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `SSEBENCH_DEMO_WEBUI_PORT` | `3001` | Port of the web UI on `127.0.0.1`. |
| `SSEBENCH_DEMO_CATALOG_PORT` | `8090` | Port of the catalog service on `127.0.0.1`. |
| `LITELLM_PORT` | `4000` | Port of the LiteLLM proxy. |
| `SSEBENCH_DEMO_PROJECT` | `ssebench-demo` | Compose project of the demo. Give it a name of its own: `just demo-down` deletes the project's volume. |
| `SSEBENCH_WEBUI_TERMINAL` | `0` in the demo | `1` turns on the terminal into the run container. |

The demo stops early, and names the variable, when a port is taken. It can run
next to the stack of `just launch`, which is a different Compose project, when
their ports differ: `LITELLM_PORT=4001 just demo`.

## Troubleshooting

- **A port is in use.** Set the variable named in the message.
- **`fail Disk`, `fail Docker` and other failed checks.** The message under the
  check says how to fix it; `just doctor` shows the same checks.
- **The run failed.** The demo prints the end of the run's log, and its path
  under `results/`. The stack keeps running, so you can look at it, and
  `just demo-down` removes it.
- **The web UI does not list the run, or says the Docker daemon is not
  reachable.** The web UI container mounts `/var/run/docker.sock`, so the
  daemon's socket has to be there, and the engine has to run containers on the
  host's network namespace.
- **A pull fails with `denied` or `not found`.** The registry does not have the
  images of this version, as before a release. The demo builds them.
- **You changed the code and the demo shows the old behavior.** Images that
  exist locally are not pulled or rebuilt: use `just demo --build`.

## Security

The web UI can stop and remove SSEBench containers and read their logs and
files, so it is bound to `127.0.0.1` and, in the demo, has no terminal. It
runs as a container that has the Docker socket, which is root access to the
host: run the demo on a machine you control, and see
[Web UI security](/webui/security). The catalog listens on `127.0.0.1` as well.
The LiteLLM proxy listens on `127.0.0.1` at `LITELLM_PORT`, as it does for
`just launch` (`LITELLM_BIND` sets another address), and asks for the master key
from `.env` for everything but its health check.

## Next steps

- [Quickstart](/getting-started/quickstart): run any agent on any task with the CLI
- [Web UI](/webui/): launch runs and inspect them
- [Reference runs](/reference/cli#reference-runs): how the `reference` agent works
