---
outline: deep
---

# Plugins and hooks

A plugin is a program that runs inside the task container before, during or
after the agent phase or grading, for example to collect extra artifacts or to
analyse the agent's patch once the run is graded. Plugins never change the
grade: a plugin that fails or runs out of time is logged and recorded, and the
run goes on as if it were not there.

To write one, see [Write a plugin](/guides/write-a-plugin).

## Declaring plugins

Each plugin is a folder in `runtime/plugins/` with an executable `run.sh`, and
an entry in `runtime/plugins/plugins.yaml`:

```yaml
- name: artifact        # the folder name
  enabled: false        # run it in every run
  hook: after-grading   # when it runs
  llm: false            # whether it gets the run's model
  timeout: 5            # minutes before it is stopped
```

`runtime/plugins/schema.json` is the file's JSON Schema; every key is required
and no others are allowed. [Configuration files](/reference/configuration#plugins-yaml)
lists the keys. The CLI validates the file when it builds the tool layer, and
the entrypoint validates it again when the container starts; an invalid file
stops the run before the agent starts.

SSEBench ships two plugins, both disabled by default:

| Plugin | Hook | What it does |
|---|---|---|
| `artifact` | `after-grading` | Writes `artifact/manifest.json`: every file in the results directory with its size, SHA-256 and the component that wrote it. |
| `oracle` | `after-grading` | Asks the run's model to compare the agent's patch with the reference patch and writes the review to `oracle/`; it can also try to fuzz the patched project. Needs a model; experimental. See `runtime/plugins/oracle/README.md`. |

## Choosing plugins for a run

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
  --agent dummy --model claude-sonnet-4-6 --plugin artifact
```

- `--plugin NAME`, repeatable, runs exactly the named plugins in this run.
- Without `--plugin`, the plugins whose `enabled` is `true` run.

The CLI installs the selected plugins into the tool image, passes the choice to
the container as `SSE_PLUGINS` when `--plugin` is given, and records it as
`config.plugins` in the [run summary](/concepts/results#the-summary). Plugins
run in sandbox mode only; `--plugin` with `--mode sidecar` is an error.

## Hooks

`hook` is `before`, `on` or `after`, joined to `agent` or `grading`:

- **before** and **after** plugins block the run until they finish or time out;
- **on** plugins start with the phase and run next to it; the runtime waits for
  them when the phase ends, before it goes on.

Plugins at the same hook run in parallel. A run goes through the hooks in this
order:

```
before-agent      blocking, as model
on-agent          started with the agent, as model; awaited when the agent exits
                  -- the agent phase ends; the reference patch unlocks --
after-agent       blocking, as model
before-grading    blocking, as root
on-grading        started with the evaluator, as root; awaited when it exits
after-grading     blocking, as root
                  -- plugins/results.json is written --
```

The hooks are part of the entrypoint's `Runtime`: `RunAgent` runs the agent
hooks around the agent, and `Evaluate` the grading hooks around the evaluator.
Any [container mode](/guides/extension-points#container-modes) that uses them,
including a third-party one, runs plugins.

## Which user a plugin runs as

| Hooks | User | Why |
|---|---|---|
| `before-agent`, `on-agent`, `after-agent` | `model` | They run around the agent and next to it. As the agent's own user they can reach nothing the agent cannot: not the task files in `/ssebench`, not `/ssebench-repo`, not the admin socket. A plugin in the agent phase therefore has no hidden material it could leak into the agent's workspace. |
| `before-grading`, `on-grading`, `after-grading` | root | Grading starts after the agent has exited, so there is no agent left to leak to, and post-run tooling needs what grading needs: the task files and the reference patch. |

Two more rules keep plugins from changing the grade:

- An `on-agent` plugin must finish before the agent phase ends. It runs as
  `model`, which owns the source tree that grading reads; a plugin still
  running when the reference patch unlocks could otherwise change that tree.
- The plugin code in the image is owned by root and not writable by `model`,
  so the agent cannot change a plugin that later runs as root.

## The contract

When its hook comes, the entrypoint runs the plugin's `run.sh` with Bash:

| | |
|---|---|
| Working directory | The plugin's folder, `/plugins/<name>` in the tool image |
| User | See [above](#which-user-a-plugin-runs-as) |
| Standard output and error | `plugins/<name>.log` in the archive directory |
| Time limit | `timeout` minutes, after which its whole process group is killed |
| Environment | The entrypoint's own environment, plus `SSE_PLUGIN_NAME`, `SSE_PLUGIN_HOOK` (such as `after-grading`) and `SSE_PLUGIN_SKIP_FILE` (see [Skipping](#skipping)); a plugin that runs as `model` has `HOME=/home/model`, `USER` and `LOGNAME` set to `model` |

The environment includes `SSE_ARCHIVE` (the results directory),
`SSE_DIFFICULTY`, `TIMEOUT` and `SSE_DAEMON_SOCKET`, the daemon's agent-facing
socket, through which [`sse`](/reference/python-sdk) reaches the daemon. The
LLM variables `SSE_BASE_URL`, `SSE_API_KEY` and `SSE_MODEL_NAME` are removed
unless the plugin declares `llm: true`, so a plugin only gets the run's model
key when it asks for it. Its model calls use the run's key, so they count
towards the run's `spend` in the summary.

A plugin writes its output under `SSE_ARCHIVE`, by convention in a folder
named after the plugin; the shipped plugins write to `artifact/` and
`oracle/`. When the plugins are done, the entrypoint gives the owner of the
results directory everything in it, so the files plugins wrote as root or
`model` can be removed on the host.

## Skipping

A plugin that cannot do its job, for example because it needs a model and the
run has none, says so instead of exiting silently: it writes the reason to the
file named by `SSE_PLUGIN_SKIP_FILE` and exits with 0. The entrypoint then
records the plugin as `skipped` with that reason, and logs it as a warning in
the container's output, which `ssebench run` shows:

```
level=WARN msg="Plugin skipped" plugin=oracle reason="No LLM configured (SSE_API_KEY, SSE_BASE_URL unset)"
```

From a shell plugin:

```bash
echo "no compiler in the image" > "$SSE_PLUGIN_SKIP_FILE"
exit 0
```

The file works for a plugin that runs as `model` too. It counts only when the
plugin exits with 0 and wrote some text; a plugin that exits with another status
is `failed` whatever the file holds.

## Outcomes

The entrypoint records every plugin run in `plugins/results.json` in the run's
`archive/` directory, and `ssebench run` copies the outcomes into
`plugin_results` of the [run summary](/concepts/results#the-summary):

```json
[
  {
    "name": "artifact",
    "hook": "after-grading",
    "status": "ok",
    "exit_code": 0,
    "duration_seconds": 0.02,
    "started": true
  }
]
```

| `status` | Meaning |
|---|---|
| `ok` | `run.sh` exited with 0 |
| `skipped` | `run.sh` exited with 0 after [saying it skipped itself](#skipping); `reason` has why |
| `failed` | It exited with another status; `exit_code` has it and `error` the reason |
| `timeout` | It ran longer than `timeout` minutes and was killed; `exit_code` is 124 |
| `error` | It could not start, for example because its folder or `run.sh` is missing from the image |

None of these changes `result.json` or the container's exit status, which is
the agent's.

## Installation in the tool image

The sandbox tool layer (`images/sandbox/Dockerfile`) always installs
`plugins.yaml` and `schema.json` in `/plugins`, and for each selected plugin
copies its folder to `/plugins/<name>`. A plugin with a `pyproject.toml` is a
member of the repository's uv workspace, named `ssebench-plugin-<name>`; the
layer syncs it into its own virtual environment, `/plugins/<name>/.venv`, as it
does for the evaluator, and its `run.sh` runs `.venv/bin/python`. That Python
lives in root's home, which only root can read, so a Python plugin runs at the
grading hooks only; a plugin in the agent phase is a shell script or brings its
own runtime.
