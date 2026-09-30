---
outline: deep
---

# Runner backends

`ssebench run` splits a run into two parts. The **runner** decides what the run
is: which images it uses, the environment and files of its containers, their
labels, and how the results are recorded. A **backend** carries that out on a
container platform. The runner calls the backend's interface and nothing else, so
a run can execute somewhere other than the local Docker daemon, for example as a
Job on Kubernetes, without changes to the runner.

```
ssebench run
   |  RunSpec                 images, environment, files, labels, network policy
   v
Runner ---------> Backend ---------> containers
   ^                 |
   |  exit status,   |  prepare_images   start   wait   logs
   |  results        |  collect_results  stop    cleanup   list_runs
   +-----------------+  endpoint         exec_argv
                          ^
ssebench runs, web UI ----+   find, watch, stop and reach runs that exist
```

The same interface serves the tools that watch runs. [`ssebench runs`](#watching-runs)
lists, stops and removes runs, and finds the address of a running run's daemon,
by calling the backend, so the [web UI](/webui/) works with every backend.

The Docker backend is built in and is the default. Others are installed as
[extensions](/guides/extension-points#runner-backends) and selected with
`ssebench run --backend NAME` or `SSEBENCH_BACKEND`.

## The run specification

A run is described by a `RunSpec`, a frozen dataclass in `ssebench.extensions`.
A backend must give the container the environment, the files and the labels
below and put it on the network the policy names; it may add what its platform
needs.

| Field | Meaning |
|---|---|
| `run_id`, `task_name`, `mode` | The run's ID (`--run-id`), the task, and `sandbox` or `sidecar`. |
| `image` | The image of the container the run waits for: the whole run in sandbox mode, the agent runtime in sidecar mode. |
| `env` | The environment of that container: the run's model key and proxy URL, the difficulty, the timeout and the paths of the [container contract](/guides/extension-points#environment-variables). It holds a secret, so it is left out of the dataclass's `repr`; never log it. |
| `results` | The run directory, mounted at `/var/lib/ssebench/results`. Root-only in the container: it holds the grade. |
| `archive` | The run directory's `archive/`, mounted at `/tmp/sse-archive`. It belongs to the agent's user. |
| `artifacts` | Read-only files for the container. For the `reference` agent this is the reference patch, at `/reference/patch.diff`; for every other agent it is empty. |
| `network` | A `NetworkPolicy`: `restricted` reaches the LiteLLM proxy and nothing else, and `open` also has internet access (`--egress`). |
| `platform` | The `linux/<arch>` platform of every image and container of the run, or `None` for the backend's own. |
| `labels` | Labels of the container the [web UI](/webui/) lists; see [Labels](#labels). |
| `timeout` | How long the agent may run, in seconds. The container enforces it itself; a backend can derive a hard deadline from it. |
| `keep` | Leave the containers and volumes in place when the run ends (`--keep-container`). |
| `sidecar` | Sidecar mode only: a `SidecarPair`, described below. |

A `Mount` names a place in the container, a `target`, and where its content
comes from, a `source`: a path on the runner's host (`kind="bind"`) or the name
of a volume (`kind="volume"`). A backend with no access to the runner's host
does not use a bind `source` as a path. It gives the container storage of its
own at the `target` and, for `artifacts`, the file's content.

### Sidecar runs

In [sidecar mode](/concepts/sandbox-and-sidecar#sidecar-mode) a run is two
containers. `RunSpec.image` is the agent container, which the run waits for. The
`SidecarPair` describes the other one and what they share:

- `environment_image`: the task container with the daemon. It starts first and
  keeps running until the agent container exits.
- `source_dir`: the project's source path, the same in both containers.
- `volumes`: the two run-scoped volumes, one for the source tree and one for the
  daemon's sockets. Both containers mount them, and the backend creates them
  before the containers start and removes them afterwards.
- `shared_env()`, `environment_env()` and `shared_mounts(results, archive)`:
  what both containers get, what the environment container alone gets, and the
  four mounts both share. The agent container never mounts the task's own files.
- `run_id`: an ID of the pair, which its containers and volumes carry as the
  `ssebench.run` label.

The environment container carries `RunSpec.labels`; the agent container carries
the pair's label only. On a platform where two containers can share volumes only
inside a pod, both belong to one.

## The interface

A backend subclasses `Backend`. It holds no state between calls: what it needs to
control a run is in the `RunHandle` that `start` returns, and it finds runs again
by their labels.

| Method | Contract |
|---|---|
| `prepare_images(request) -> Images` | Make the run's images available and return their names. With `request.prebuilt`, pull or check the [published images](#prebuilt-images); otherwise build the layers. Raises `UserError` when a layer fails to build or an image cannot be found. |
| `copy_from_image(image, path, dest, platform)` | Copy one file out of an image without starting a run. The runner uses it to get the reference patch. Raises `RuntimeError` on failure. |
| `start(spec) -> RunHandle` | Start the run and return once its containers exist. From then on the container's output goes to this process's stdout and stderr as it is written. When it raises `BackendError`, nothing of the run is left behind. |
| `wait(handle, timeout) -> int` | Wait for the container the run waits for to exit and return its exit status. A stopped container ends with 128 plus the signal, 143 for the SIGTERM of `stop`. Raises `TimeoutError`. |
| `logs(handle, follow=False)` | Yield the container's output, stdout and stderr together, one line at a time; with `follow`, until it exits. |
| `collect_results(handle, dest)` | Put the run's results in `dest`, the run directory on the runner's host, once the container has exited. See [Results](#results). |
| `stop(handle, grace)` | Ask the containers to stop and kill them after `grace` seconds. Safe to call at any time, also before the container has started. |
| `cleanup(handle)` | Remove what the run left: containers, volumes, other objects. Best effort. Does nothing for a run started with `keep`. |
| `list_runs(labels) -> list[RunInfo]` | The runs that carry every label in `labels`, running or not. |
| `inspect_run(run_id) -> RunInfo \| None` | The run with that `ssebench.run-id` label. It has a default implementation on top of `list_runs`. |
| `endpoint(handle, port) -> str` | `http://host:port`, at which the machine that calls this reaches `port` of the run's container. Optional; see [Reaching a run](#reaching-a-run). |
| `exec_argv(handle, command, ...) -> list[str]` | The argument vector of a local command that runs `command` in the run's container. Optional; see [Reaching a run](#reaching-a-run). |
| `proxy() -> ProxyEndpoint \| None` | Optional. The backend's own LiteLLM proxy, as the two URLs `host_url` (where `ssebench run` reaches it to create the run's key) and `service_url` (the run's `SSE_BASE_URL`). The default, `None`, is the local Compose stack, which `ssebench run` starts. A backend that returns an endpoint owns the proxy, and the runner starts no stack and does not check the provider keys on this host. |

`RunInfo` has the run ID, the name, a `state` (`created`, `running`, `exited` or
`unknown`), the exit code once it exited, the image, the labels, when the
container was created (`created_at`, an ISO 8601 string, if the backend knows)
and a `RunHandle` that the other methods accept. Errors a caller can act on are
`BackendError` (a run that cannot be started or watched), `UserError` and
`ImageUnavailableError` (an image that cannot be prepared). Messages must not
contain the run's environment.

`Backend.builds_images` says whether `prepare_images` can build layers. A backend
that cannot, such as one that only runs prebuilt images on a cluster, leaves it
`False`, and `ssebench run` then requires `--prebuilt`.

### Reaching a run

A tool that watches a run needs to talk to what runs in its container. The
[web UI](/webui/run-view) reads the SSEBench daemon (port 4263) and the OpenCode
server (port 4096) of a running run, and opens a shell in it. Two methods of the
backend cover that. Neither is abstract, so a backend that does not implement
them still works for everything else; they raise `BackendError`.

`endpoint(handle, port)` returns a URL, `http://host:port`, at which **the
machine that calls it** reaches `port` of the run's container. What that is
depends on the platform:

- On Docker it is the container's address on its Docker network. It is
  routable from a Linux host, not from Docker Desktop.
- On a cluster it is a Service or a pod address when the caller is inside the
  cluster, and a forwarded port on `127.0.0.1` when it is not.

The URL has to stay valid after the call returns, and after the process that
made it exits, because the tools that call it are short-lived commands
(`ssebench runs endpoint`). A backend that needs a port-forward therefore runs
one that outlives the call and reuses it on the next call. The URL carries no
credentials: the daemon's agent-facing API is unauthenticated, so it has to be
reachable only by the caller. Raise `BackendError` if the run is not running.

`exec_argv(handle, command, user=, workdir=, tty=, stdin=, env_names=)` returns
the argument vector of a command that the caller runs locally with its standard
streams attached, for example `docker exec ...` or `kubectl exec ...`. `command`
reaches the container as separate arguments and is never parsed by a shell.
`env_names` are variables that the container's process gets with the values they
have in the caller's environment; their values must not appear in the vector,
which a process listing shows, so a backend that cannot pass them otherwise
raises. A backend that implements it sets `supports_exec = True`. The web UI
opens its terminal and starts its assistant only on such a backend.

### Watching runs

`ssebench runs` is the command-line and JSON front of the interface above, for
people and for tools. It selects the backend as `ssebench run` does
(`--backend`, or `SSEBENCH_BACKEND`), and names a run by its run ID:

| Command | Does |
|---|---|
| `runs list [--json]` | Lists the runs the backend has, running or not. `--json` prints `{"backend", "supports_exec", "runs"}`. |
| `runs inspect ID [--json]` | Shows one run. Exits with status 3 if there is none, and 4 if several runs have that ID. |
| `runs logs ID [--follow]` | Prints the container's output. |
| `runs stop ID [--grace SECONDS]` | Stops the run's containers and leaves them in place. |
| `runs remove ID` | Removes what the run left, running or not. |
| `runs endpoint ID PORT [--json]` | Prints the URL from `endpoint`. |
| `runs exec ID [options] -- COMMAND...` | Replaces the process with the command from `exec_argv`. |
| `runs results [--json] [--dir DIR]` | Lists the finished runs in `results/`, whether or not their containers still exist. It reads files and needs no backend. |

See [CLI](/reference/cli#ssebench-runs) for the options.

### What the runner does around it

For one run, the runner:

1. calls `prepare_images` once (`ssebench run` does this before it starts the
   run);
2. creates the run directory and its `archive/`, and for the `reference` agent
   asks the backend to copy the patch out of an image;
3. calls `start`, `wait`, `collect_results` and `cleanup`, in this order, and
   calls `cleanup` also when `wait` is interrupted;
4. records the run: `result.json` gets the run's settings, and `summary.json`
   is written beside it. It does this also when the container failed, was
   stopped, or produced no grade.

When the CLI gets SIGTERM or SIGINT during `wait`, it calls `stop` on the run,
waits for the container to exit, and records the run as usual. A second signal
ends the process.

## Results

The container writes its results to two directories: the run directory, with the
grade (`result.json`), the graded patch and the logs, and its `archive/`, with
the agent's own files. The layout is that of the [results
format](/concepts/results).

The runner does not assume where those directories live. A backend either:

- shares the storage with the runner, as the Docker backend does by
  bind-mounting the run directory; `collect_results` then has nothing to do; or
- keeps the results in its own storage, such as a volume or an object store, and
  copies them into `dest` in `collect_results`. `dest` already holds the
  skeleton the runner made (`archive/` and an empty `result.json`), and the files
  the container wrote replace it.

Either way, when `collect_results` returns, `dest` holds what the container
wrote. The runner then reads `result.json` and the exit status to decide how to
record the run.

## Labels

A tool finds the runs of `ssebench run` by label, through `list_runs` and
`inspect_run`. The container the web UI lists carries:

| Label | Value |
|---|---|
| `ssebench.run-id` | The run's ID |
| `ssebench.webui` | `true` |
| `ssebench.task-id` | The task |
| `ssebench.model` | The model, or `none` |
| `ssebench.agent` | The agent |
| `ssebench.results` | The run directory on the runner's host |
| `ssebench.reference-run` | `true` for a reference run only |

A backend that has no labels on its objects, such as a Job, can use its own
equivalent, as long as `list_runs` accepts these keys. `ssebench runs list` asks
for `ssebench.webui=true`, which the runner puts on every run.

## Prebuilt images

By default `ssebench run` builds the tool and agent layers on every run, on top
of the case image. With `--prebuilt`, or `SSEBENCH_PREBUILT=1`, it uses images
that were built ahead of time and published under `SSEBENCH_REGISTRY`, and
builds nothing. This is the mode for a backend that cannot build, such as a
Kubernetes cluster that pulls images onto its nodes.

A prebuilt run needs one image per agent and task, the same one a build ends
with, named by the [image layers](/concepts/image-layers#the-layers):

| Mode | Image |
|---|---|
| sandbox | `<registry>/agent-<agent>/<task-id>:<agent version>`: the agent on the tool layer on the case image |
| sidecar | `<registry>/agent-<agent>/sidecar:<agent version>` and `<registry>/tool-sidecar/<task-id>:<version>` |

`prebuilt_images(request)` in `ssebench.extensions` computes the names, so a
backend and the tool that publishes the images agree. The Docker backend pulls
them for the run's platform and, if a pull fails but the image is already on the
machine, warns and uses that copy.

The images carry their tool layer and plugins as they were built, so
`--prebuilt` excludes `--tool-layer`, `--plugin` and `--build`, and ignores the
plugins that `plugins.yaml` enables. The task still comes from `--local` or a
catalog for its metadata; the case image is not needed. A reference run takes
the reference patch from the image it runs.

Nothing publishes these images yet. To make them for a task and an agent:

1. build the case image: `ssebench build-case --tasks <task-id>`;
2. build the tool and agent layers on it, which `ssebench run` does before it
   starts a container, and which `docker buildx build` does with the
   Dockerfiles described in [Image layers](/concepts/image-layers);
3. push the images under the names above, in a registry the backend can pull
   from.

## The Docker backend

`DockerBackend` runs the containers on the Docker daemon that the `docker` CLI
is set up for. It builds the layers with `docker buildx`, and starts the run
with `docker run`:

- the task container runs in the foreground of a `docker run` process, so its
  output reaches the terminal as it is written, and is removed on exit unless the
  run is kept;
- the run directory and its `archive/` are bind-mounted, and the reference patch
  is mounted read-only;
- the container joins the agents network of the LiteLLM stack for `restricted`
  egress and the default network for `open`. `DockerBackend(network=NAME)` joins
  another network;
- in sidecar mode the environment container starts detached first, with its
  volumes, and is removed together with them when the run ends.

## Write a backend

Subclass `Backend`, implement the methods above, and register the class as an
entry point. The [extension points](/guides/extension-points#runner-backends)
page shows how. A backend is created without arguments. This skeleton shows the
shape; `LoggingBackend` in `bench/tests/fixtures/ssebench_example_ext` is a
complete one that extends `DockerBackend`.

```python
from ssebench.extensions import Backend, ImageRequest, Images, RunHandle, RunSpec, prebuilt_images


class ClusterBackend(Backend):
    name = "cluster"          # builds_images stays False: prebuilt images only

    def prepare_images(self, request: ImageRequest) -> Images:
        return prebuilt_images(request)

    def start(self, spec: RunSpec) -> RunHandle:
        ...                   # create the Job; stream its pod's log to stdout

    # ... wait, logs, collect_results, stop, cleanup, list_runs, copy_from_image

    # Optional, for the web UI: reach the daemon, and open a terminal
    # def endpoint(self, handle, port): ...
    # def exec_argv(self, handle, command, **options): ...
```

To test one, run the runner against it in a unit test, as
`bench/tests/test_backend.py` does with a fake backend, and check a real run with
`ssebench run --backend NAME --prebuilt` on a `reference` agent, which needs no
model.
