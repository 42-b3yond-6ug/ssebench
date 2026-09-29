---
outline: deep
---

# Launching runs

The launch wizard starts runs from the browser. It collects a task, a model, an
agent and an execution mode, then runs `uv run ssebench run --keep-container`
once per task, in the SSEBench checkout that the web UI serves. What a launched
run does is what [`ssebench run`](/reference/cli#ssebench-run) does, so
everything on that page applies.

The wizard needs the web UI to run from a checkout, as in `just webui`. The
[container image](/webui/#in-a-container) has no checkout and no `uv`, so it
can show runs but not launch them.

## Before you launch

The wizard does not start anything that the command line would not. Have these
ready first:

- **`.env`** with the proxy secrets and the key of your model's provider.
  `just setup` writes the file; see [Local stack](/deployment/compose). The run
  starts the [LiteLLM proxy](/concepts/litellm-proxy) if it is not running.
- **Docker**, `uv` and the images the task needs. The first launch of a task
  builds its case image, which can take minutes; the launch output shows the
  build.
- **A model that works.** The wizard lists every model in `models/*.yaml`
  without checking that its provider key is set. A model without a key fails
  when the agent first calls it. The `dummy` and `reference` agents make no
  model calls, so they need no key.

## The wizard

Click **Launch New Test** in the sidebar or on the home page. The **Launch**
tab of the dialog has five steps, and a step needs a choice before **Next**
works. **Back**, the step tabs and the **Edit** links on the last step return to
an earlier step.

![The task step of the launch wizard, with a local task selected](/images/webui/launch-task.png)

### 1. Task

Pick one or more tasks from one of two sources:

| Tab | Lists | Set by |
|---|---|---|
| **Catalog** | The tasks of the [task catalog](/reference/cli#task-catalog), with their language | `SSEBENCH_CATALOG`, else the bundled pilot manifest |
| **Local** | The task folders of a dataset directory | `SSEBENCH_LOCAL_TASKS`, else `datasets/pilot` in the checkout |

A tab is disabled when its source has no tasks: **Catalog** shows `off` when no
catalog is configured, and `SSEBENCH_CATALOG` can be the path or URL of a
manifest, a dataset directory, or a catalog service. Both variables are listed
in [Environment variables](/reference/environment#web-ui).

The search box filters by task ID, language or project. The list shows the first
100 matches, and **Select all** selects only those. Switching tabs clears the
selection.

A catalog task runs like `ssebench run --catalog <location>`: its case image is
pulled from the registry, and built from the task folder if the pull fails. A
local task runs like `--local <directory>` and always builds its case image from
the folder.

### 2. Model

The models of `models/*.yaml`, grouped by provider. The first model in
alphabetical order is selected when the step opens, so check the choice before
you go on. To add a model, see [Add a model](/guides/add-a-model).

The `reference` agent makes no model calls, but the wizard still asks for a
model. The CLI ignores it with a warning, and the run's model is `none`.

### 3. Agent

One card per directory under `agents/`: `claude-code`, `codex`, `dummy`,
`opencode` and `reference` at the time of writing, and any agent you
[add](/guides/add-an-agent). `claude-code` is selected first. The cards show a
description only for `claude-code` and `codex`.

### 4. Mode

**Sandbox** runs the agent and the SDK in one container. **Sidecar** runs them in
two, and is experimental; see [Sandbox and sidecar](/concepts/sandbox-and-sidecar).

### 5. Review

![The review step, with the command the launch corresponds to](/images/webui/launch-review.png)

The summary lists the choices, and the preview shows the command each task
corresponds to. The button reads **Launch Task**, or **Launch N Tasks** when you
selected several.

Launching several tasks starts all their `ssebench run` processes at once, with
no limit. Each builds images and starts a container, so a large selection can
exhaust the host's CPU, memory or disk.

## Options the wizard does not offer

The wizard passes the model, agent, task, mode and task source, and nothing
else. Runs it starts use the CLI defaults for every other option:

| Option | Value in a launched run |
|---|---|
| `--difficulty` | 2, `NO_FUTURE_TEST` |
| `--timeout` | 3600 seconds |
| `--egress` | `restricted` |
| `--plugin` | the plugins that `plugins.yaml` enables |
| `--tool-layer` | `sandbox` |

To change one of them, start the run from the command line with
`--keep-container` and attach to it, as described in [Watching a
run](/webui/run-view#runs-from-the-command-line).

## What a launch does

Each launched task runs

```sh
uv run ssebench run --model=<model> --agent=<agent> --task=<task> \
    --mode=<mode> --keep-container --local=<directory>
```

with `--catalog=<location>` instead of `--local` for a catalog task. The command
runs in `SSEBENCH_PATH` (the checkout, by default the directory above `webui/`)
with the environment of the web UI server, so `COMPOSE_PROJECT_NAME`,
`LITELLM_PORT` and `SSEBENCH_REGISTRY` in that environment or in `.env` decide
which proxy stack and images the run uses. The arguments are passed as an
argument vector, never through a shell.

The server accepts only a model from `models/`, an agent from `agents/`, and
a local task from the local dataset. It rejects anything else with a `400`.

## Following a launch

Each launch gets a card in the sidebar that reads **Launching...** with the task
ID. While it is there:

- Click the card to read the output of the command: the proxy start, the image
  builds, then the container's output. The view keeps the last 5000 lines and
  shows the command at the top, including the absolute path of the checkout.
- **Cancel** (the cross on the card, or the button in the view) stops the
  launch. It works only until the container exists.
- A launch that fails turns the card red, with the exit code, for example
  `Process exited with code 1`. The output tells why; **Dismiss** removes the
  card.

While a launch runs, the bottom **Logs** tab of the run you are looking at shows
a **Launching** badge. Those logs belong to that run, not to the launch; the
launch output is in the sidebar card.

When the run's container appears, the card is replaced by a tab for the run. The
web UI switches to it if you were watching the launch, and otherwise leaves your
view alone. See [Watching a run](/webui/run-view).

The web UI finds the run's container by its task ID: it takes the newest container
that has the label `ssebench.task-id` set to the task.

::: warning
If a container for the same task already exists on the Docker daemon, running or
exited, the web UI may take it for the new run. It then attaches to that
container and ends the launch before the new container exists, and the run you
asked for never starts. Containers of other users and of other Compose projects
count too. Remove your finished containers of a task before launching it again,
and on a Docker daemon that others share, start runs from the command line.
:::

## What a launched run leaves behind

The container of a launched run stays after grading, because of
`--keep-container`. When it appears, the web UI ends the `ssebench run` process
that started it; the container keeps going.

So a launched run:

- writes `results/<task>/<model>/<agent>/` in the checkout as usual, since the
  container writes it: `result.json`, `dialog.jsonl`, `final.patch` and the
  logs;
- does not write the summary `results/<task>-<agent>-<model>.json` or read the
  model spend from the proxy, since the process that does that no longer exists.
  [Results format](/concepts/results) describes both.

To record a run with its summary, start it from the command line. With
`--keep-container`, the CLI keeps running until the container stops, and then
writes the summary.

Stop the container when you have looked at it; see
[Containers](/webui/run-view#containers). A kept container serves its API,
including the reference patch, for as long as it runs.

### Sidecar runs

A sidecar run with `--keep-container` keeps two containers and two volumes, all
labelled `ssebench.run`. The web UI tracks the task container, which holds the
daemon. The agent container has no web UI label and is not listed. Remove both
containers and both volumes yourself when you are done.

::: warning
In sidecar mode the grade is written in the agent container, which the daemon in
the task container cannot read. The **Evaluation Result** tab of a sidecar run
stays empty; read `result.json` in `results/` instead.
:::

## Next steps

- [Watching a run](/webui/run-view): the dialog, the diff, the terminal and the
  grade
- [Security model](/webui/security): who can launch runs
- [CLI](/reference/cli#ssebench-run): every option of `ssebench run`
