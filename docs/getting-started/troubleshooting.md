---
outline: deep
---

# Troubleshooting

Start with `ssebench doctor`. It checks what a run needs from your machine, and
prints a fix for each problem it finds. The sections below follow its checks,
then the failures that only show up during a run.

## Start with `ssebench doctor`

From a clone, run `just doctor`; without one, run `uvx ssebench doctor` in the
directory that `ssebench init` set up.

```text
  ok    SSEBench home  /home/you/ssebench
  ok    Docker         daemon 29.8.0
  ok    buildx         v0.31.1
  ok    Compose        5.4.0
  ok    CPU            x86_64
  ok    Disk           553 GiB free on /var/lib/docker
  ok    .env           /home/you/ssebench/.env
  warn  LiteLLM        no answer at http://localhost:4000/health/liveliness (Compose project ssebench)
                       fix: `ssebench run` starts the proxy when needed; start it now with `ssebench proxy up` (`just launch` in a checkout). If another program uses port 4000, set LITELLM_PORT in .env.
  warn  Provider keys  missing: ANTHROPIC_API_KEY (7 models), GOOGLE_API_KEY (2 models), OPENAI_API_KEY (4 models)
                       fix: Put the key of each provider you use in .env (the proxy reads keys only from there), then restart the proxy with `ssebench proxy up`. The dummy and reference agents need no key.

All required checks passed (2 warning(s)).
```

`ok` means the check passed. `fail` marks a problem that stops runs, with a
`fix:` line under it, and makes the command exit with status 1. `warn` marks
something to know about; it does not change the exit status. The two warnings
above are normal on a fresh setup: the proxy starts with your first run, and
you only need the key of the provider you use.

| Check | What it looks at | Section |
|---|---|---|
| `SSEBench home` | Where the CLI finds `agents/`, `images/` and the Compose file: your checkout, or the copy in the package | [Working directory](/reference/cli#working-directory) |
| `Docker`, `buildx`, `Compose` | `docker version`, `docker buildx version`, `docker compose version` | [Docker, buildx and Compose](#docker-buildx-and-compose) |
| `CPU` | The machine's architecture | [CPU architecture](#cpu-architecture) |
| `Disk` | Free space where Docker keeps its images | [Disk space](#disk-space) |
| `.env` | That `.env` exists and holds the proxy secrets | [`.env` and the secrets](#env-and-the-secrets) |
| `LiteLLM` | Whether the proxy answers on its port | [The LiteLLM proxy](#the-litellm-proxy) |
| `Provider keys` | Which of the keys that `models/*.yaml` refers to are set in `.env` | [Provider keys](#provider-keys) |

## Docker, buildx and Compose

SSEBench needs a running Docker daemon that your user can reach, the buildx
plugin (every image is built with `docker buildx build`) and the Compose plugin
(the LiteLLM proxy is a Compose stack).

```text
  fail  Docker         failed to connect to the docker API at unix:///nonexistent; check if the path is correct and if the daemon is running: dial unix /nonexistent: connect: no such file or directory
                       fix: Install Docker, start the daemon, and make sure your user can reach it (`docker info`).
```

- **The daemon does not answer.** Start it (`sudo systemctl start docker` on
  most Linux systems, or start Docker Desktop), then check with `docker info`.
  If `DOCKER_HOST` is set, it must point at a daemon that runs.
- **`permission denied while trying to connect to the Docker daemon socket`.**
  Your user is not allowed to use the daemon. Add it to the `docker` group
  (`sudo usermod -aG docker "$USER"`) and log in again. On NixOS, set
  `virtualisation.docker.enable = true;` and add `"docker"` to your user's
  `extraGroups`.
- **`fail buildx` or `fail Compose`.** Install the plugins:
  `docker-buildx` and `docker-compose-plugin` in most Linux package managers,
  or a current Docker Desktop. `docker buildx version` and
  `docker compose version` must both print a version.
- **Docker Desktop and other engines that run containers in a VM** have not
  been tested with [the demo](/getting-started/demo), whose web UI container
  shares the host's network.

## CPU architecture

```text
  warn  CPU            This host is aarch64, so tasks that support only amd64 run under amd64 emulation: their case image, the tool layer and the agent all build and run as linux/amd64. That is slow, and AddressSanitizer may misbehave under QEMU.
                       fix: Use an x86-64 host. To run here, Docker must be able to run amd64 images: Docker Desktop can, and on Linux `docker run --privileged --rm tonistiigi/binfmt --install amd64` installs QEMU's handlers.
```

All 55 pilot tasks build amd64 images, and many C tasks compile with
AddressSanitizer for x86-64 only. On an ARM64 host, a run builds and runs the
whole task under amd64 emulation, which is slower and where some tasks fail.
Use an x86-64 host for benchmark runs. `docker run --rm --platform linux/amd64
alpine uname -m` prints `x86_64` when your Docker can run amd64 images; if it
fails with `exec format error`, install the emulator. `ssebench run` and
`ssebench build-case` print the same warning once. See
[Architectures](/getting-started/installation#architectures).

## Disk space

`ssebench doctor` looks at the file system that holds Docker's images, not at
your working directory. It fails below 10 GiB free and warns below 50 GiB.

The three base images take 3.5 to 5 GB, the LiteLLM proxy 1.2 to 1.7 GB, and
every task adds its case image (0.7 to 3.4 GB, half of them under 1.3 GB) plus the
tool and agent layers on top of it; the [sizes](/getting-started/installation#prerequisites)
depend on the Docker version. Many tasks share layers, so `docker system df`
shows what Docker really uses. Its `Build Cache` row is often the largest: about
11 GB after a demo built from the checkout.

- `docker builder prune --all` frees the build cache and touches no image,
  container or volume. The next build starts cold and takes longer.
- `just case-clean` removes every case image. They are pulled or built again
  the next time a task needs them.
- Move Docker's data to a larger disk with `data-root` in
  `/etc/docker/daemon.json`.
- `results/` also grows: every run keeps a copy of the source tree.

## `.env` and the secrets

`.env` holds the LiteLLM master key, the Postgres password and your provider
keys. `just setup` writes it in a clone, and `ssebench init` writes it in the
directory you run from without one.

```text
  fail  .env           /home/you/ssebench-work/.env not found
                       fix: Run `ssebench init` (`just setup` in a checkout).
```

A command that needs the secrets says the same thing:

```text
ERROR:ssebench.cli.cli:LITELLM_MASTER_KEY is not set. Run `ssebench init` (`just setup` in a checkout) to write .env with generated local secrets, or set LITELLM_MASTER_KEY in the environment.
```

Without a clone, `ssebench` reads `.env` in the **working directory**, so run it
from the directory that `ssebench init` set up. `ssebench init` never overwrites
an existing file.

**The proxy exits because the database volume has another password.**
Postgres applies `POSTGRES_PASSWORD` only when it creates its volume. If `.env`
holds another password afterwards, the proxy cannot log in to the database and
exits. This happens after you change the password, and when a second workspace
(a checkout, or a directory set up by `ssebench init`) uses the same Compose
project, `ssebench` by default, with its own generated `.env`. The command stops
as soon as the proxy container has exited, and prints the end of the proxy's
log:

```text
ERROR:ssebench.cli.cli:The LiteLLM proxy container exited before it became healthy (Compose project ssebench).

The database volume ssebench_postgres_data was created with another POSTGRES_PASSWORD than the one in .env, because Postgres keeps the password it was created with. Put the old password back in .env, or start with a new database by running `ssebench proxy down --volumes` (it deletes the proxy's stored keys and spend records), or give this workspace its own COMPOSE_PROJECT_NAME.
```

The database's log (`docker logs ssebench-litellm_db-1`) says
`password authentication failed for user "litellm"`. Put the old password back
in `.env`, or remove the database volume and let Postgres create a new one:

```sh
ssebench proxy down --volumes         # just stop keeps the volume
ssebench proxy up                     # or: just launch
```

Or keep both databases: set `COMPOSE_PROJECT_NAME` (and `LITELLM_PORT`, if both
run at once) to a value of its own in the `.env` of the second workspace. The
volume is named `<COMPOSE_PROJECT_NAME>_postgres_data`. Removing it deletes the
proxy's database, with the keys and the spend records of earlier runs.

## The LiteLLM proxy

Every agent reaches its model through the [LiteLLM proxy](/concepts/litellm-proxy),
which runs as a Compose stack. `ssebench run` starts it when it is not running,
so `warn LiteLLM no answer` is normal before your first run. To start or stop it
yourself, use `just launch` and `just stop`, or `ssebench proxy up` and
`ssebench proxy down`.

- **`Bind for 0.0.0.0:4000 failed: port is already allocated`.** Another
  program, or another SSEBench stack, uses the port. Choose another with
  `LITELLM_PORT` in `.env`. A second stack also needs a Compose project of its
  own, `COMPOSE_PROJECT_NAME`, so that the two do not share containers and the
  database volume; stacks with different names and ports run side by side.
- **The proxy exited, or does not become healthy within 180 seconds.** A proxy
  that exited is reported at once, with the end of its log. Otherwise look at it
  yourself, `docker logs ssebench-litellm-1` (`<project>-litellm-1` when you set
  `COMPOSE_PROJECT_NAME`). The most common cause is the Postgres password;
  see [`.env` and the secrets](#env-and-the-secrets).
- **`docker ps` says the proxy container is `unhealthy`.** Trust `ssebench doctor`,
  or `curl http://localhost:4000/health/liveliness`, which answers
  `"I'm alive!"`, rather than the container's own health status.
- **You changed `models/`.** `ssebench run` and `ssebench proxy up` rebuild the
  proxy image when a file in `models/` changed, and `ssebench proxy up --rebuild`
  forces it. See [Add a model](/guides/add-a-model).

## Provider keys

The proxy reads the keys of the model providers from `.env` only. A key that is
set in your shell does not count, and `ssebench doctor` says so:

```text
  warn  Provider keys  set: ANTHROPIC_API_KEY (7 models); missing: GOOGLE_API_KEY (2 models), OPENAI_API_KEY (4 models)
```

Put the key of the provider you use in `.env`, then restart the proxy so that it
picks the key up:

```sh
ssebench proxy up      # just launch
```

Missing keys are only a problem for the models that need them: the `dummy` and
`reference` agents need none, and both `ssebench run` and
`just demo --agent <agent> --model <model>` stop before they build anything when
the model's key is missing from `.env`, with one line that names the variable.

### The agent ended at once, or said it could not log in

`ssebench run` stops before it builds anything when `.env` lacks the model's
provider key, but it cannot tell whether a key that is there works. A run whose
provider key is wrong still builds the images and runs the agent, and ends with
a grade, so check the run when it finishes much sooner than an agent working on
a task would. The signs:

- `result.json` says `failed`, with `PoC failed` as `error_msg`, because the
  agent changed nothing, and the summary's `spend` is 0.
- `dialog.jsonl` ends with a message from the agent instead of a fix, and
  `agent.log` shows what went wrong. With no key at all, Claude Code says
  `Not logged in · Please run /login`. With a wrong key, it says
  `Failed to authenticate. API Error: 401 litellm.AuthenticationError:
  AnthropicException - ... API key is invalid`. The agent retries the request a
  few times first, so this takes about three minutes to show.

Fix the key in `.env`, restart the proxy with `ssebench proxy up`, and run again.

## Running a task

- **`Unknown model 'no-such-model'. Available models: ...`** The name is not in
  `models/*.yaml`; the message lists the names, and the closest one when there
  is one.
- **`Unknown agent 'no-such-agent'. Available agents: ...`** The name is not a
  directory under `agents/`. SSEBench ships `claude-code`, `codex`, `opencode`,
  `dummy` and `reference`.
- **`Model '<name>': <VARIABLE> is not set in .env.`** The model's provider key
  is missing; see [Provider keys](#provider-keys).
- **`Benchmark task no-such-task does not exist.`** With `--local DIR`, the
  task is not a folder of that directory. `uv run ssebench tasks list` prints
  the task IDs.
- **`Cannot pull <image>, and there is no local copy of task <id> to build it
  from.`** Without `--local`, the case image is pulled from the registry
  (`SSEBENCH_REGISTRY`). The pull failed, because you are offline or the
  registry does not have the image, and a package install has no task folder to
  build it from. Check your network and `SSEBENCH_REGISTRY`, or use a clone and
  run the task from its dataset: `just run` adds `--local datasets/pilot`, which
  builds the case image from the task's folder.
- **A build cannot pull a base image.** Case images build on
  `base-generic-c`, `base-generic-go` or `base-generic-rust`. Docker pulls the
  one a task pins, and `just base-images` builds all three yourself, which also
  helps when you are offline.
- **A case image fails to build.** The task's `Dockerfile` clones the upstream
  project at a pinned commit and downloads its dependencies, so a build needs the
  network and the upstream repositories to still exist. Pulling the published case
  image, that is running without `--local`, avoids the build.
- **A task fails because it needs the internet.** A run container reaches the
  LiteLLM proxy but not the internet. A task whose tests download something
  needs `--egress open`; see [Integrity and egress](/deployment/integrity-and-egress).
- **A run takes a long time.** The agent works until it stops or reaches
  `--timeout` (3600 seconds by default). `agent.log` and `daemon.log` in
  `results/<task>/<model>/<agent>/latest/` grow while it works, and the [web UI](/webui/)
  shows the dialog live.
- **You want to clean up.** `just stop` stops the proxy and keeps its database,
  and `just demo-down` removes the demo. Run containers that were kept for the
  web UI show up in `docker ps --filter label=ssebench.webui=true`;
  remove them with `docker rm -f`.

## The demo

[Try the demo](/getting-started/demo#troubleshooting) lists what can go wrong
with `just demo`: a port in use, images that are not in the registry yet, and a
web UI that cannot reach Docker.

## Still stuck

Open an [issue](https://github.com/42-b3yond-6ug/ssebench/issues) with the
output of `ssebench doctor`, the output of `ssebench --version`, the command you
ran and the end of its output. The logs in the run's directory under `results/`
(`agent.log`, `daemon.log`, `evaluator.log`) help too; check them for keys and
private data first. Report a way for an agent to reach the reference answer
privately, as [SECURITY.md](https://github.com/42-b3yond-6ug/ssebench/blob/main/SECURITY.md)
describes.
